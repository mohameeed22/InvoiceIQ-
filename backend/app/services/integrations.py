"""
Google Sheets & Airtable Integration Services
-----------------------------------------------
Google Sheets:
    Requires a Service Account JSON file from Google Cloud Console.
    Set GOOGLE_SERVICE_ACCOUNT_JSON=/path/to/credentials.json and GOOGLE_SHEET_ID=<sheet_id> in .env

Airtable:
    Requires AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_TABLE_NAME in .env
"""
import json
from typing import Dict, Any, List
from datetime import datetime
from app.config import settings
from app.models import Document


# ─── Currency symbol map ───────────────────────────────────────────────────────
CURRENCY_SYMBOLS = {
    "USD": "$", "EUR": "€", "GBP": "£", "TND": "DT",
    "CAD": "CA$", "AUD": "A$", "JPY": "¥", "CHF": "CHF",
}


def _build_row(document: Document) -> List[Any]:
    """Builds a flat data row list for Sheets/CSV export from a Document model."""
    ext = document.extraction
    if not ext:
        return [document.id, document.filename, document.status, "", "", "", "", "", "", "", "", "", ""]
    return [
        document.id,
        document.filename,
        document.status,
        ext.vendor_name,
        ext.vendor_address,
        ext.invoice_number,
        ext.invoice_date,
        ext.due_date,
        ext.currency,
        ext.subtotal,
        ext.tax_amount,
        ext.total_amount,
        ext.confidence_score,
        "Yes" if ext.math_valid else "No",
        "Yes" if ext.is_duplicate else "No",
        ext.extraction_provider,
        document.created_at.strftime("%Y-%m-%d %H:%M") if document.created_at else "",
    ]


def _build_airtable_record(document: Document) -> Dict[str, Any]:
    """Builds an Airtable record fields dict from a Document model."""
    ext = document.extraction
    fields: Dict[str, Any] = {
        "Document ID": document.id,
        "Filename": document.filename,
        "Status": document.status,
        "Uploaded At": document.created_at.isoformat() if document.created_at else "",
    }
    if ext:
        fields.update({
            "Vendor Name": ext.vendor_name,
            "Invoice Number": ext.invoice_number,
            "Invoice Date": ext.invoice_date,
            "Due Date": ext.due_date,
            "Currency": ext.currency,
            "Subtotal": ext.subtotal,
            "Tax Amount": ext.tax_amount,
            "Total Amount": ext.total_amount,
            "Confidence Score (%)": ext.confidence_score,
            "Math Valid": ext.math_valid,
            "Duplicate": ext.is_duplicate,
            "Extraction Provider": ext.extraction_provider,
        })
    return fields


# ─── Google Sheets ─────────────────────────────────────────────────────────────

SHEETS_HEADERS = [
    "Doc ID", "Filename", "Status", "Vendor Name", "Vendor Address",
    "Invoice #", "Invoice Date", "Due Date", "Currency",
    "Subtotal", "Tax", "Total", "Confidence %", "Math Valid",
    "Duplicate", "Provider", "Uploaded At"
]


def export_to_google_sheets(document: Document, sheet_id: str = None) -> Dict[str, Any]:
    """
    Appends extracted invoice data to a Google Sheet.
    Creates a header row if the sheet is empty.

    Args:
        document: The Document ORM object (with .extraction relationship loaded).
        sheet_id: Optional override for the target sheet ID (uses settings.GOOGLE_SHEET_ID by default).

    Returns:
        dict with keys: success (bool), sheet_url (str or None), error (str or None)
    """
    target_sheet_id = sheet_id or settings.GOOGLE_SHEET_ID
    creds_path = settings.GOOGLE_SERVICE_ACCOUNT_JSON

    if not target_sheet_id:
        return {"success": False, "error": "GOOGLE_SHEET_ID is not configured in .env"}
    if not creds_path:
        return {"success": False, "error": "GOOGLE_SERVICE_ACCOUNT_JSON is not configured in .env"}

    try:
        import gspread
        from google.oauth2.service_account import Credentials

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
        client = gspread.authorize(creds)

        spreadsheet = client.open_by_key(target_sheet_id)
        worksheet = spreadsheet.sheet1

        # Write headers if the sheet is empty
        existing = worksheet.get_all_values()
        if not existing or existing[0] != SHEETS_HEADERS:
            if not existing:
                worksheet.append_row(SHEETS_HEADERS, value_input_option="USER_ENTERED")
            else:
                worksheet.insert_row(SHEETS_HEADERS, 1)

        # Append document row
        row = _build_row(document)
        worksheet.append_row(row, value_input_option="USER_ENTERED")

        sheet_url = f"https://docs.google.com/spreadsheets/d/{target_sheet_id}"
        return {
            "success": True,
            "sheet_url": sheet_url,
            "rows_appended": 1,
        }

    except ImportError:
        return {"success": False, "error": "gspread not installed. Run: pip install gspread google-auth"}
    except FileNotFoundError:
        return {"success": False, "error": f"Service account JSON not found at: {creds_path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def batch_export_to_google_sheets(documents: List[Document], sheet_id: str = None) -> Dict[str, Any]:
    """Appends multiple documents to a Google Sheet in one batch call."""
    target_sheet_id = sheet_id or settings.GOOGLE_SHEET_ID
    creds_path = settings.GOOGLE_SERVICE_ACCOUNT_JSON

    if not target_sheet_id:
        return {"success": False, "error": "GOOGLE_SHEET_ID is not configured in .env"}
    if not creds_path:
        return {"success": False, "error": "GOOGLE_SERVICE_ACCOUNT_JSON is not configured in .env"}

    try:
        import gspread
        from google.oauth2.service_account import Credentials

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
        client = gspread.authorize(creds)

        spreadsheet = client.open_by_key(target_sheet_id)
        worksheet = spreadsheet.sheet1

        existing = worksheet.get_all_values()
        if not existing or existing[0] != SHEETS_HEADERS:
            if not existing:
                worksheet.append_row(SHEETS_HEADERS, value_input_option="USER_ENTERED")

        rows = [_build_row(doc) for doc in documents]
        worksheet.append_rows(rows, value_input_option="USER_ENTERED")

        return {
            "success": True,
            "sheet_url": f"https://docs.google.com/spreadsheets/d/{target_sheet_id}",
            "rows_appended": len(rows),
        }

    except ImportError:
        return {"success": False, "error": "gspread not installed."}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── Airtable ──────────────────────────────────────────────────────────────────

def export_to_airtable(document: Document, base_id: str = None, table_name: str = None) -> Dict[str, Any]:
    """
    Creates a new record in an Airtable base for the extracted invoice.

    Args:
        document: The Document ORM object.
        base_id: Optional Airtable base ID override.
        table_name: Optional table name override.

    Returns:
        dict with keys: success (bool), record_id (str or None), error (str or None)
    """
    target_base = base_id or settings.AIRTABLE_BASE_ID
    target_table = table_name or settings.AIRTABLE_TABLE_NAME
    api_key = settings.AIRTABLE_API_KEY

    if not api_key:
        return {"success": False, "error": "AIRTABLE_API_KEY is not configured in .env"}
    if not target_base:
        return {"success": False, "error": "AIRTABLE_BASE_ID is not configured in .env"}

    try:
        from pyairtable import Api as AirtableApi

        client = AirtableApi(api_key)
        table = client.table(target_base, target_table)

        fields = _build_airtable_record(document)
        result = table.create(fields)

        return {
            "success": True,
            "record_id": result.get("id"),
            "airtable_url": f"https://airtable.com/{target_base}/{target_table}",
        }

    except ImportError:
        return {"success": False, "error": "pyairtable not installed. Run: pip install pyairtable"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def batch_export_to_airtable(documents: List[Document], base_id: str = None, table_name: str = None) -> Dict[str, Any]:
    """Creates multiple Airtable records in one batch operation (max 10 per Airtable API)."""
    target_base = base_id or settings.AIRTABLE_BASE_ID
    target_table = table_name or settings.AIRTABLE_TABLE_NAME
    api_key = settings.AIRTABLE_API_KEY

    if not api_key:
        return {"success": False, "error": "AIRTABLE_API_KEY not configured."}
    if not target_base:
        return {"success": False, "error": "AIRTABLE_BASE_ID not configured."}

    try:
        from pyairtable import Api as AirtableApi

        client = AirtableApi(api_key)
        table = client.table(target_base, target_table)

        records_created = []
        # Airtable batch limit is 10 records per call
        batch_size = 10
        for i in range(0, len(documents), batch_size):
            batch = documents[i:i + batch_size]
            fields_batch = [_build_airtable_record(doc) for doc in batch]
            results = table.batch_create(fields_batch)
            records_created.extend([r.get("id") for r in results])

        return {
            "success": True,
            "records_created": len(records_created),
            "record_ids": records_created,
            "airtable_url": f"https://airtable.com/{target_base}/{target_table}",
        }

    except ImportError:
        return {"success": False, "error": "pyairtable not installed."}
    except Exception as e:
        return {"success": False, "error": str(e)}
