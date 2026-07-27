import hashlib
from typing import Tuple, Dict, Any, List, Optional
from sqlalchemy.orm import Session
from app.models import Document, ExtractionResult

def compute_file_hash(file_path: str) -> str:
    """Calculates SHA-256 hash of document file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    return sha256.hexdigest()

def check_for_duplicates(
    db: Session, 
    file_hash: str, 
    vendor_name: str = "", 
    invoice_number: str = "",
    current_doc_id: Optional[int] = None
) -> Tuple[bool, Optional[int]]:
    """
    Checks if a document is a duplicate based on:
    1. Exact SHA-256 file hash match.
    2. Same vendor name and non-empty invoice number.
    """
    # 1. Check exact hash
    query = db.query(Document).filter(Document.file_hash == file_hash)
    if current_doc_id:
        query = query.filter(Document.id != current_doc_id)
    existing_hash_doc = query.first()
    
    if existing_hash_doc:
        return True, existing_hash_doc.id

    # 2. Check vendor + invoice number match
    if vendor_name and invoice_number:
        existing_result = db.query(ExtractionResult).filter(
            ExtractionResult.vendor_name.ilike(vendor_name.strip()),
            ExtractionResult.invoice_number.ilike(invoice_number.strip())
        )
        if current_doc_id:
            existing_result = existing_result.filter(ExtractionResult.document_id != current_doc_id)
        match = existing_result.first()
        if match:
            return True, match.document_id

    return False, None

def validate_extraction_integrity(
    vendor_name: str,
    invoice_number: str,
    invoice_date: str,
    subtotal: float,
    tax_amount: float,
    discount_amount: float,
    total_amount: float,
    line_items: List[Dict[str, Any]]
) -> Tuple[float, str, bool]:
    """
    Validates document mathematical consistency and computes extraction confidence score.
    Returns: (confidence_score, confidence_status, math_valid)
    """
    score = 100.0
    math_valid = True

    # 1. Essential Field Presence Checks
    if not vendor_name or vendor_name.strip() in ["", "Unknown Vendor"]:
        score -= 15.0

    if not invoice_number or invoice_number.strip() in ["", "N/A", "NONE"]:
        score -= 10.0

    if not invoice_date or invoice_date.strip() == "":
        score -= 10.0

    if total_amount <= 0:
        score -= 25.0

    # 2. Total Math Validation: (subtotal - discount + tax) vs total_amount
    expected_total = round(subtotal - discount_amount + tax_amount, 2)
    actual_total = round(total_amount, 2)

    if subtotal > 0 and total_amount > 0:
        diff = abs(expected_total - actual_total)
        # Allow small rounding float discrepancy (<= 0.05)
        if diff > 0.05:
            score -= 20.0
            math_valid = False

    # 3. Line items sum check vs subtotal
    if line_items and subtotal > 0:
        line_items_sum = round(sum(item.get("total_price", 0.0) for item in line_items), 2)
        if abs(line_items_sum - round(subtotal, 2)) > 0.1:
            score -= 10.0

    # Clamp score between 0.0 and 100.0
    score = max(0.0, min(100.0, round(score, 1)))

    # Determine status level
    if score >= 85.0 and math_valid:
        status = "HIGH"
    elif score >= 60.0:
        status = "NEEDS_REVIEW"
    else:
        status = "FLAG"

    return score, status, math_valid
