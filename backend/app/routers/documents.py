import os
import shutil
import json
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, Response, Query
from fastapi.responses import PlainTextResponse, JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import settings
from app.auth import require_api_key
from app.models import Document, ExtractionResult, LineItem, AuditLog
from app.schemas import (
    DocumentSchema, DocumentDetailSchema, ManualVerificationRequest,
    WebhookTriggerRequest
)
from app.services.preprocessing import DocumentPreprocessor
from app.services.validator import compute_file_hash, check_for_duplicates, validate_extraction_integrity
from app.services.ai_extractor import AIVisionExtractor
from app.services.categorizer import auto_categorize_line_item
from app.services.exporter import DocumentExporter
from app.services.integrations import (
    export_to_google_sheets, batch_export_to_google_sheets,
    export_to_airtable, batch_export_to_airtable
)


router = APIRouter(prefix="/documents", tags=["Documents"])


async def _run_extraction_pipeline(doc_id: int, saved_path: str, preprocessed_path: str, mime_type: str):
    """
    Background task: runs AI extraction, validation, and duplicate detection
    for an already-saved document. Updates document status when done.
    """
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            return

        try:
            raw_extracted = await AIVisionExtractor.extract_document_data(preprocessed_path, mime_type)
        except Exception as e:
            doc.status = "error"
            db.add(AuditLog(document_id=doc_id, action="EXTRACTION_ERROR", details=str(e)))
            db.commit()
            return

        raw_items = raw_extracted.get("line_items", [])
        line_items_data = []
        for item in raw_items:
            desc = item.get("description", "Item")
            qty = float(item.get("quantity", 1.0))
            u_price = float(item.get("unit_price", 0.0))
            t_price = float(item.get("total_price", qty * u_price))
            cat = item.get("category") or auto_categorize_line_item(desc)
            line_items_data.append({"description": desc, "quantity": qty,
                                     "unit_price": u_price, "total_price": t_price, "category": cat})

        subtotal = float(raw_extracted.get("subtotal", 0.0))
        tax = float(raw_extracted.get("tax_amount", 0.0))
        discount = float(raw_extracted.get("discount_amount", 0.0))
        total = float(raw_extracted.get("total_amount", 0.0))
        vendor = raw_extracted.get("vendor_name", "")
        inv_num = raw_extracted.get("invoice_number", "")

        conf_score, conf_status, math_valid = validate_extraction_integrity(
            vendor_name=vendor, invoice_number=inv_num,
            invoice_date=raw_extracted.get("invoice_date", ""),
            subtotal=subtotal, tax_amount=tax, discount_amount=discount,
            total_amount=total, line_items=line_items_data
        )
        is_dup, dup_id = check_for_duplicates(db, doc.file_hash, vendor, inv_num, doc.id)

        ext_res = ExtractionResult(
            document_id=doc_id,
            vendor_name=vendor,
            vendor_address=raw_extracted.get("vendor_address", ""),
            invoice_number=inv_num,
            invoice_date=raw_extracted.get("invoice_date", ""),
            due_date=raw_extracted.get("due_date", ""),
            currency=raw_extracted.get("currency", "USD"),
            subtotal=subtotal, tax_amount=tax, discount_amount=discount,
            total_amount=total,
            detected_language=raw_extracted.get("detected_language", "English"),
            confidence_score=conf_score, confidence_status=conf_status,
            math_valid=math_valid, is_duplicate=is_dup, duplicate_of_id=dup_id,
            raw_json=json.dumps(raw_extracted),
            extraction_provider=raw_extracted.get("extraction_provider", "mock")
        )
        db.add(ext_res)

        for item in line_items_data:
            db.add(LineItem(document_id=doc_id, description=item["description"],
                            quantity=item["quantity"], unit_price=item["unit_price"],
                            total_price=item["total_price"], category=item["category"]))

        doc.status = "extracted"
        db.add(AuditLog(
            document_id=doc_id, action="EXTRACTED",
            details=f"Extracted via {ext_res.extraction_provider} with score {conf_score}%"
        ))
        db.commit()
    finally:
        db.close()

@router.post("/upload", response_model=List[DocumentDetailSchema], dependencies=[Depends(require_api_key)])
async def upload_documents(
    files: List[UploadFile] = File(...),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db)
):
    """
    Accepts single or batch documents (PDF, JPG, PNG, WEBP).
    Runs preprocessing, vision LLM extraction, math validation, and duplicate detection.
    """
    processed_docs = []

    for file in files:
        # Save raw file
        filename = file.filename or "uploaded_document"
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safe_filename = f"{timestamp}_{filename.replace(' ', '_')}"
        saved_path = os.path.join(settings.UPLOAD_DIR, safe_filename)

        with open(saved_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        file_size = os.path.getsize(saved_path)
        mime_type = file.content_type or "image/png"
        file_hash = compute_file_hash(saved_path)

        # Create Document record with "queued" status for async processing
        doc = Document(
            filename=filename,
            file_path=saved_path,
            file_hash=file_hash,
            file_size=file_size,
            mime_type=mime_type,
            status="processing"
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

        # Preprocessing (deskew, denoise, normalize)
        preprocessed_path = DocumentPreprocessor.preprocess_image(saved_path)

        # Run extraction inline (synchronous for now to return result immediately)
        # Vision AI Extraction
        try:
            raw_extracted = await AIVisionExtractor.extract_document_data(preprocessed_path, mime_type)
        except Exception as e:
            doc.status = "error"
            db.commit()
            raise HTTPException(status_code=400, detail=str(e))

        # Extract items
        raw_items = raw_extracted.get("line_items", [])
        line_items_data = []
        for item in raw_items:
            desc = item.get("description", "Item")
            qty = float(item.get("quantity", 1.0))
            u_price = float(item.get("unit_price", 0.0))
            t_price = float(item.get("total_price", qty * u_price))
            cat = item.get("category") or auto_categorize_line_item(desc)
            
            line_items_data.append({
                "description": desc,
                "quantity": qty,
                "unit_price": u_price,
                "total_price": t_price,
                "category": cat
            })

        # Math & Confidence Check
        subtotal = float(raw_extracted.get("subtotal", 0.0))
        tax = float(raw_extracted.get("tax_amount", 0.0))
        discount = float(raw_extracted.get("discount_amount", 0.0))
        total = float(raw_extracted.get("total_amount", 0.0))
        vendor = raw_extracted.get("vendor_name", "")
        inv_num = raw_extracted.get("invoice_number", "")

        conf_score, conf_status, math_valid = validate_extraction_integrity(
            vendor_name=vendor,
            invoice_number=inv_num,
            invoice_date=raw_extracted.get("invoice_date", ""),
            subtotal=subtotal,
            tax_amount=tax,
            discount_amount=discount,
            total_amount=total,
            line_items=line_items_data
        )

        # Duplicate Check
        is_dup, dup_id = check_for_duplicates(db, file_hash, vendor, inv_num, doc.id)

        # Save Extraction Result
        ext_res = ExtractionResult(
            document_id=doc.id,
            vendor_name=vendor,
            vendor_address=raw_extracted.get("vendor_address", ""),
            invoice_number=inv_num,
            invoice_date=raw_extracted.get("invoice_date", ""),
            due_date=raw_extracted.get("due_date", ""),
            currency=raw_extracted.get("currency", "USD"),
            subtotal=subtotal,
            tax_amount=tax,
            discount_amount=discount,
            total_amount=total,
            detected_language=raw_extracted.get("detected_language", "English"),
            confidence_score=conf_score,
            confidence_status=conf_status,
            math_valid=math_valid,
            is_duplicate=is_dup,
            duplicate_of_id=dup_id,
            raw_json=json.dumps(raw_extracted),
            extraction_provider=raw_extracted.get("extraction_provider", "mock")
        )
        db.add(ext_res)

        # Save Line Items
        for item in line_items_data:
            db_item = LineItem(
                document_id=doc.id,
                description=item["description"],
                quantity=item["quantity"],
                unit_price=item["unit_price"],
                total_price=item["total_price"],
                category=item["category"]
            )
            db.add(db_item)

        # Update Document status
        doc.status = "extracted"
        
        # Add Audit log
        audit = AuditLog(
            document_id=doc.id,
            action="EXTRACTED",
            details=f"Extracted via {ext_res.extraction_provider} with score {conf_score}%"
        )
        db.add(audit)
        
        db.commit()
        db.refresh(doc)
        processed_docs.append(doc)

    return processed_docs

@router.get("", response_model=List[DocumentSchema])
def list_documents(
    status: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """Lists uploaded documents with optional status filter and full-text search."""
    query = db.query(Document)
    if status:
        query = query.filter(Document.status == status)
    if search:
        search_term = f"%{search.strip()}%"
        query = query.join(Document.extraction, isouter=True).filter(
            Document.filename.ilike(search_term)
            | ExtractionResult.vendor_name.ilike(search_term)
            | ExtractionResult.invoice_number.ilike(search_term)
        )
    docs = query.order_by(Document.created_at.desc()).offset(offset).limit(limit).all()
    return docs

@router.get("/{document_id}", response_model=DocumentDetailSchema)
def get_document(document_id: int, db: Session = Depends(get_db)):
    """Retrieves document detail including extraction result and line items."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc

@router.put("/{document_id}/verify", response_model=DocumentDetailSchema)
def update_manual_verification(
    document_id: int,
    payload: ManualVerificationRequest,
    db: Session = Depends(get_db)
):
    """Updates manually corrected fields or line items and marks document as verified."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc or not doc.extraction:
        raise HTTPException(status_code=404, detail="Document or extraction not found")

    ext = doc.extraction
    updates = payload.extraction

    # Update Extraction fields
    ext.vendor_name = updates.vendor_name
    ext.vendor_address = updates.vendor_address
    ext.invoice_number = updates.invoice_number
    ext.invoice_date = updates.invoice_date
    ext.due_date = updates.due_date
    ext.currency = updates.currency
    ext.subtotal = updates.subtotal
    ext.tax_amount = updates.tax_amount
    ext.discount_amount = updates.discount_amount
    ext.total_amount = updates.total_amount
    ext.detected_language = updates.detected_language

    # Re-run math & confidence check after manual edit
    line_items_list = []
    if updates.line_items is not None:
        # Delete existing line items and replace
        db.query(LineItem).filter(LineItem.document_id == doc.id).delete()
        for item in updates.line_items:
            cat = item.category or auto_categorize_line_item(item.description)
            db_item = LineItem(
                document_id=doc.id,
                description=item.description,
                quantity=item.quantity,
                unit_price=item.unit_price,
                total_price=item.total_price,
                category=cat
            )
            db.add(db_item)
            line_items_list.append({
                "description": item.description,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "total_price": item.total_price,
                "category": cat
            })
    else:
        line_items_list = [
            {
                "description": li.description,
                "quantity": li.quantity,
                "unit_price": li.unit_price,
                "total_price": li.total_price,
                "category": li.category
            }
            for li in doc.line_items
        ]

    conf_score, conf_status, math_valid = validate_extraction_integrity(
        vendor_name=ext.vendor_name,
        invoice_number=ext.invoice_number,
        invoice_date=ext.invoice_date,
        subtotal=ext.subtotal,
        tax_amount=ext.tax_amount,
        discount_amount=ext.discount_amount,
        total_amount=ext.total_amount,
        line_items=line_items_list
    )

    ext.confidence_score = conf_score
    ext.confidence_status = conf_status
    ext.math_valid = math_valid

    if payload.mark_verified:
        doc.status = "verified"

    # Audit log entry
    audit = AuditLog(
        document_id=doc.id,
        action="MANUALLY_VERIFIED",
        details="User verified and updated fields."
    )
    db.add(audit)

    db.commit()
    db.refresh(doc)
    return doc

@router.delete("/{document_id}", dependencies=[Depends(require_api_key)])
def delete_document(document_id: int, db: Session = Depends(get_db)):
    """Deletes a document and associated data."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if os.path.exists(doc.file_path):
        try:
            os.remove(doc.file_path)
        except Exception:
            pass

    db.delete(doc)
    db.commit()
    return {"message": "Document deleted successfully"}


@router.post("/{document_id}/retry", response_model=DocumentDetailSchema, dependencies=[Depends(require_api_key)])
async def retry_extraction(document_id: int, db: Session = Depends(get_db)):
    """Retries AI extraction on a document that has status 'error'."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.status not in ("error", "processing"):
        raise HTTPException(status_code=400, detail=f"Document is not in an error state (status: {doc.status})")

    # Reset status and delete old (potentially partial) extraction
    doc.status = "processing"
    if doc.extraction:
        db.delete(doc.extraction)
    db.query(LineItem).filter(LineItem.document_id == doc_id).delete()
    db.commit()

    preprocessed_path = DocumentPreprocessor.preprocess_image(doc.file_path)
    try:
        raw_extracted = await AIVisionExtractor.extract_document_data(preprocessed_path, doc.mime_type)
    except Exception as e:
        doc.status = "error"
        db.commit()
        raise HTTPException(status_code=400, detail=str(e))

    raw_items = raw_extracted.get("line_items", [])
    line_items_data = []
    for item in raw_items:
        desc = item.get("description", "Item")
        qty = float(item.get("quantity", 1.0))
        u_price = float(item.get("unit_price", 0.0))
        t_price = float(item.get("total_price", qty * u_price))
        cat = item.get("category") or auto_categorize_line_item(desc)
        line_items_data.append({"description": desc, "quantity": qty,
                                 "unit_price": u_price, "total_price": t_price, "category": cat})

    subtotal = float(raw_extracted.get("subtotal", 0.0))
    tax = float(raw_extracted.get("tax_amount", 0.0))
    discount = float(raw_extracted.get("discount_amount", 0.0))
    total = float(raw_extracted.get("total_amount", 0.0))
    vendor = raw_extracted.get("vendor_name", "")
    inv_num = raw_extracted.get("invoice_number", "")

    conf_score, conf_status, math_valid = validate_extraction_integrity(
        vendor_name=vendor, invoice_number=inv_num,
        invoice_date=raw_extracted.get("invoice_date", ""),
        subtotal=subtotal, tax_amount=tax, discount_amount=discount,
        total_amount=total, line_items=line_items_data
    )
    is_dup, dup_id = check_for_duplicates(db, doc.file_hash, vendor, inv_num, doc.id)

    ext_res = ExtractionResult(
        document_id=doc.id, vendor_name=vendor,
        vendor_address=raw_extracted.get("vendor_address", ""),
        invoice_number=inv_num, invoice_date=raw_extracted.get("invoice_date", ""),
        due_date=raw_extracted.get("due_date", ""), currency=raw_extracted.get("currency", "USD"),
        subtotal=subtotal, tax_amount=tax, discount_amount=discount, total_amount=total,
        detected_language=raw_extracted.get("detected_language", "English"),
        confidence_score=conf_score, confidence_status=conf_status, math_valid=math_valid,
        is_duplicate=is_dup, duplicate_of_id=dup_id,
        raw_json=json.dumps(raw_extracted),
        extraction_provider=raw_extracted.get("extraction_provider", "mock")
    )
    db.add(ext_res)

    for item in line_items_data:
        db.add(LineItem(document_id=doc.id, description=item["description"],
                        quantity=item["quantity"], unit_price=item["unit_price"],
                        total_price=item["total_price"], category=item["category"]))

    doc.status = "extracted"
    db.add(AuditLog(document_id=doc.id, action="RETRY_EXTRACTION",
                    details=f"Re-extracted via {ext_res.extraction_provider} score={conf_score}%"))
    db.commit()
    db.refresh(doc)
    return doc

@router.get("/{document_id}/export/csv")
def export_csv(document_id: int, db: Session = Depends(get_db)):
    """Downloads CSV export of extracted document."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    csv_content = DocumentExporter.to_csv(doc)
    headers = {"Content-Disposition": f'attachment; filename="invoiceiq_{document_id}.csv"'}
    return PlainTextResponse(content=csv_content, media_type="text/csv", headers=headers)

@router.get("/{document_id}/export/json")
def export_json(document_id: int, db: Session = Depends(get_db)):
    """Downloads JSON export of extracted document."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    qb_payload = DocumentExporter.to_quickbooks_format(doc)
    return JSONResponse(content=qb_payload)

@router.post("/{document_id}/export/webhook", dependencies=[Depends(require_api_key)])
async def trigger_webhook(
    document_id: int,
    payload: WebhookTriggerRequest,
    db: Session = Depends(get_db)
):
    """Triggers external n8n/Zapier webhook POST with extracted JSON payload."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    url = payload.webhook_url or settings.DEFAULT_WEBHOOK_URL
    if not url:
        raise HTTPException(status_code=400, detail="No webhook URL provided.")

    result = await DocumentExporter.dispatch_webhook(url, doc)
    return result


@router.post("/{document_id}/export/sheets", dependencies=[Depends(require_api_key)])
def export_to_sheets(
    document_id: int,
    sheet_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Exports a document's extracted data to Google Sheets."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    result = export_to_google_sheets(doc, sheet_id=sheet_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Google Sheets export failed"))
    db.add(AuditLog(document_id=doc.id, action="EXPORTED_SHEETS",
                    details=f"Exported to Google Sheet: {result.get('sheet_url')}"))
    db.commit()
    return result


@router.post("/batch/export/sheets", dependencies=[Depends(require_api_key)])
def batch_export_sheets(
    document_ids: List[int],
    sheet_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Exports multiple documents to Google Sheets in one batch operation."""
    docs = db.query(Document).filter(Document.id.in_(document_ids)).all()
    if not docs:
        raise HTTPException(status_code=404, detail="No documents found for given IDs")
    result = batch_export_to_google_sheets(docs, sheet_id=sheet_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Batch Sheets export failed"))
    return result


@router.post("/{document_id}/export/airtable", dependencies=[Depends(require_api_key)])
def export_to_airtable_endpoint(
    document_id: int,
    base_id: Optional[str] = None,
    table_name: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Exports a document's extracted data to Airtable."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    result = export_to_airtable(doc, base_id=base_id, table_name=table_name)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Airtable export failed"))
    db.add(AuditLog(document_id=doc.id, action="EXPORTED_AIRTABLE",
                    details=f"Exported to Airtable record: {result.get('record_id')}"))
    db.commit()
    return result


@router.post("/batch/export/airtable", dependencies=[Depends(require_api_key)])
def batch_export_airtable_endpoint(
    document_ids: List[int],
    base_id: Optional[str] = None,
    table_name: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Exports multiple documents to Airtable in batch."""
    docs = db.query(Document).filter(Document.id.in_(document_ids)).all()
    if not docs:
        raise HTTPException(status_code=404, detail="No documents found for given IDs")
    result = batch_export_to_airtable(docs, base_id=base_id, table_name=table_name)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Batch Airtable export failed"))
    return result


@router.get("/{document_id}/audit", dependencies=[Depends(require_api_key)])
def get_audit_log(document_id: int, db: Session = Depends(get_db)):
    """Returns the audit log history for a specific document."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    logs = db.query(AuditLog).filter(AuditLog.document_id == document_id).order_by(AuditLog.timestamp.desc()).all()
    return [
        {"id": l.id, "action": l.action, "details": l.details,
         "timestamp": l.timestamp.isoformat() if l.timestamp else ""}
        for l in logs
    ]
