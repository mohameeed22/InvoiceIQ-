from typing import List, Dict, Any, Optional
from datetime import datetime, date
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models import Document, ExtractionResult, LineItem
from app.schemas import SpendAnalyticsSummary
from app.config import settings

router = APIRouter(prefix="/analytics", tags=["Spend Analytics"])

# Approximate exchange rates to USD for normalization
EXCHANGE_RATES_TO_USD = {
    "USD": 1.0,
    "EUR": 1.09,
    "GBP": 1.27,
    "TND": 0.32,
    "CAD": 0.74,
    "AUD": 0.66,
    "JPY": 0.0067,
    "CHF": 1.13,
}


def normalize_to_base(amount: float, currency: str, base: str = "USD") -> float:
    """Converts an amount from a given currency to the base currency."""
    to_usd = EXCHANGE_RATES_TO_USD.get(currency.upper(), 1.0)
    from_usd = EXCHANGE_RATES_TO_USD.get(base.upper(), 1.0)
    return round(amount * to_usd / from_usd, 2)


@router.get("/summary", response_model=SpendAnalyticsSummary)
def get_analytics_summary(
    start_date: Optional[str] = Query(default=None, description="Filter from date YYYY-MM-DD"),
    end_date: Optional[str] = Query(default=None, description="Filter to date YYYY-MM-DD"),
    currency: Optional[str] = Query(default=None, description="Override base currency (USD, EUR, GBP, TND...)"),
    db: Session = Depends(get_db)
):
    """
    Provides high-level spend analytics across all processed documents.
    Supports optional date range filtering and base currency normalization.
    """
    base_currency = (currency or settings.BASE_CURRENCY).upper()

    query = db.query(ExtractionResult).join(Document)
    if start_date:
        try:
            dt_start = datetime.strptime(start_date, "%Y-%m-%d")
            query = query.filter(Document.created_at >= dt_start)
        except ValueError:
            pass
    if end_date:
        try:
            dt_end = datetime.strptime(end_date, "%Y-%m-%d")
            query = query.filter(Document.created_at <= dt_end)
        except ValueError:
            pass

    extractions = query.all()

    total_docs = len(extractions)

    # Normalize total spend to base currency
    total_spend = round(sum(
        normalize_to_base(e.total_amount or 0.0, e.currency or "USD", base_currency)
        for e in extractions
    ), 2)

    avg_conf = round(
        sum(e.confidence_score or 0.0 for e in extractions) / max(len(extractions), 1),
        1
    )

    # Vendor breakdown (normalized)
    vendor_map: Dict[str, Dict] = {}
    for e in extractions:
        vendor = e.vendor_name or "Unknown Vendor"
        normalized = normalize_to_base(e.total_amount or 0.0, e.currency or "USD", base_currency)
        if vendor not in vendor_map:
            vendor_map[vendor] = {"vendor": vendor, "doc_count": 0, "total_spend": 0.0}
        vendor_map[vendor]["doc_count"] += 1
        vendor_map[vendor]["total_spend"] = round(vendor_map[vendor]["total_spend"] + normalized, 2)

    vendor_breakdown = sorted(
        vendor_map.values(), key=lambda x: x["total_spend"], reverse=True
    )

    # Category breakdown (from line items, normalized)
    line_items_query = db.query(LineItem).join(
        ExtractionResult, LineItem.document_id == ExtractionResult.document_id
    )
    if start_date or end_date:
        line_items_query = line_items_query.join(Document, LineItem.document_id == Document.id)
        if start_date:
            try:
                line_items_query = line_items_query.filter(
                    Document.created_at >= datetime.strptime(start_date, "%Y-%m-%d")
                )
            except ValueError:
                pass
        if end_date:
            try:
                line_items_query = line_items_query.filter(
                    Document.created_at <= datetime.strptime(end_date, "%Y-%m-%d")
                )
            except ValueError:
                pass

    category_map: Dict[str, Dict] = {}
    for li in line_items_query.all():
        cat = li.category or "General Expense"
        # Get currency from parent extraction
        parent_ext = next((e for e in extractions if e.document_id == li.document_id), None)
        curr = parent_ext.currency if parent_ext else "USD"
        normalized = normalize_to_base(li.total_price or 0.0, curr, base_currency)
        if cat not in category_map:
            category_map[cat] = {"category": cat, "item_count": 0, "total_spend": 0.0}
        category_map[cat]["item_count"] += 1
        category_map[cat]["total_spend"] = round(category_map[cat]["total_spend"] + normalized, 2)

    category_breakdown = sorted(
        category_map.values(), key=lambda x: x["total_spend"], reverse=True
    )

    # Real monthly trend from DB — group by YYYY-MM of document.created_at
    monthly_map: Dict[str, float] = {}
    for e in extractions:
        doc = db.query(Document).filter(Document.id == e.document_id).first()
        if doc and doc.created_at:
            month_key = doc.created_at.strftime("%b %Y")
            normalized = normalize_to_base(e.total_amount or 0.0, e.currency or "USD", base_currency)
            monthly_map[month_key] = round(monthly_map.get(month_key, 0.0) + normalized, 2)

    # Sort months chronologically
    monthly_trend = []
    for month_str, spend in sorted(
        monthly_map.items(),
        key=lambda x: datetime.strptime(x[0], "%b %Y")
    ):
        monthly_trend.append({"month": month_str, "spend": spend})

    return SpendAnalyticsSummary(
        total_documents=total_docs,
        total_spend=total_spend,
        avg_confidence=avg_conf,
        currency=base_currency,
        vendor_breakdown=vendor_breakdown,
        category_breakdown=category_breakdown,
        monthly_trend=monthly_trend
    )


@router.get("/confidence-history")
def get_confidence_history(
    limit: int = Query(default=30, le=100),
    db: Session = Depends(get_db)
):
    """Returns confidence score history for charting over the last N documents."""
    results = (
        db.query(ExtractionResult, Document.filename, Document.created_at)
        .join(Document, ExtractionResult.document_id == Document.id)
        .order_by(Document.created_at.asc())
        .limit(limit)
        .all()
    )
    return [
        {
            "document_id": r[0].document_id,
            "filename": r[1],
            "confidence_score": r[0].confidence_score,
            "confidence_status": r[0].confidence_status,
            "vendor_name": r[0].vendor_name,
            "uploaded_at": r[2].strftime("%Y-%m-%d") if r[2] else "",
        }
        for r in results
    ]


@router.get("/status-breakdown")
def get_status_breakdown(db: Session = Depends(get_db)):
    """Returns counts of documents grouped by processing status."""
    results = db.query(Document.status, func.count(Document.id)).group_by(Document.status).all()
    return [{"status": s, "count": c} for s, c in results]
