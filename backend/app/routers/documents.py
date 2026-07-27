import os
import shutil
import json
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Response, Query
from fastapi.responses import PlainTextResponse, JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import settings
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

router = APIRouter(prefix="/documents", tags=["Documents"])

@router.post("/upload", response_model=List[DocumentDetailSchema])
async def upload_documents(
    files: List[UploadFile] = File(...),
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

        # Create Document record
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

        # Vision AI Extraction
        raw_extracted = await AIVisionExtractor.extract_document_data(preprocessed_path, mime_type)

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
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """Lists uploaded documents with optional status filter."""
    query = db.query(Document)
    if status:
        query = query.filter(Document.status == status)
    
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

@router.delete("/{document_id}")
def delete_document(document_id: int, db: Session = Depends(get_db)):
    """Deletes a document and associated data."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Remove file on disk if exists
    if os.path.exists(doc.file_path):
        try:
            os.remove(doc.file_path)
        except Exception:
            pass

    db.delete(doc)
    db.commit()
    return {"message": "Document deleted successfully"}

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

@router.post("/{document_id}/export/webhook")
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
