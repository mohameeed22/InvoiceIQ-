import csv
import io
import json
import httpx
from typing import Dict, Any, List, Optional
from app.models import Document, ExtractionResult, LineItem

class DocumentExporter:
    @staticmethod
    def to_csv(document: Document) -> str:
        """Exports a document and its line items to a clean CSV format."""
        output = io.StringIO()
        writer = csv.writer(output)

        # Header Metadata
        writer.writerow(["Document ID", document.id])
        writer.writerow(["Filename", document.filename])
        writer.writerow(["Status", document.status])
        
        ext = document.extraction
        if ext:
            writer.writerow(["Vendor Name", ext.vendor_name])
            writer.writerow(["Vendor Address", ext.vendor_address])
            writer.writerow(["Invoice Number", ext.invoice_number])
            writer.writerow(["Invoice Date", ext.invoice_date])
            writer.writerow(["Due Date", ext.due_date])
            writer.writerow(["Currency", ext.currency])
            writer.writerow(["Subtotal", ext.subtotal])
            writer.writerow(["Tax Amount", ext.tax_amount])
            writer.writerow(["Total Amount", ext.total_amount])
            writer.writerow(["Confidence Score (%)", ext.confidence_score])
            writer.writerow(["Math Validated", ext.math_valid])
        
        writer.writerow([])
        writer.writerow(["--- LINE ITEMS ---"])
        writer.writerow(["ID", "Description", "Quantity", "Unit Price", "Total Price", "Category"])

        for item in document.line_items:
            writer.writerow([
                item.id,
                item.description,
                item.quantity,
                item.unit_price,
                item.total_price,
                item.category
            ])

        return output.getvalue()

    @staticmethod
    def to_quickbooks_format(document: Document) -> Dict[str, Any]:
        """Formats extracted invoice into QuickBooks / Xero API compatible bill structure."""
        ext = document.extraction
        if not ext:
            return {}

        return {
            "Bill": {
                "VendorRef": {"name": ext.vendor_name},
                "DocNumber": ext.invoice_number,
                "TxnDate": ext.invoice_date,
                "DueDate": ext.due_date,
                "CurrencyRef": {"value": ext.currency},
                "TotalAmt": ext.total_amount,
                "Line": [
                    {
                        "DetailType": "AccountBasedExpenseLineDetail",
                        "Amount": item.total_price,
                        "Description": item.description,
                        "AccountBasedExpenseLineDetail": {
                            "AccountRef": {"name": item.category},
                            "UnitPrice": item.unit_price,
                            "Qty": item.quantity
                        }
                    }
                    for item in document.line_items
                ]
            }
        }

    @staticmethod
    async def dispatch_webhook(webhook_url: str, document: Document) -> Dict[str, Any]:
        """Dispatches extracted document data payload to external webhook (n8n, Zapier, Make)."""
        ext = document.extraction
        payload = {
            "event": "invoice.extracted",
            "document_id": document.id,
            "filename": document.filename,
            "status": document.status,
            "extraction": {
                "vendor_name": ext.vendor_name if ext else "",
                "invoice_number": ext.invoice_number if ext else "",
                "invoice_date": ext.invoice_date if ext else "",
                "currency": ext.currency if ext else "USD",
                "subtotal": ext.subtotal if ext else 0.0,
                "tax": ext.tax_amount if ext else 0.0,
                "total": ext.total_amount if ext else 0.0,
                "confidence_score": ext.confidence_score if ext else 0.0,
                "confidence_status": ext.confidence_status if ext else "NEEDS_REVIEW"
            },
            "line_items": [
                {
                    "description": item.description,
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                    "total_price": item.total_price,
                    "category": item.category
                }
                for item in document.line_items
            ],
            "quickbooks_payload": DocumentExporter.to_quickbooks_format(document)
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(webhook_url, json=payload)
                return {
                    "success": resp.status_code < 400,
                    "status_code": resp.status_code,
                    "response": resp.text[:200]
                }
        except Exception as e:
            return {"success": False, "error": str(e)}
