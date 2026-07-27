from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class LineItemBase(BaseModel):
    description: str
    quantity: float = 1.0
    unit_price: float = 0.0
    total_price: float = 0.0
    category: str = "General Expense"

class LineItemCreate(LineItemBase):
    pass

class LineItemSchema(LineItemBase):
    id: int
    document_id: int

    class Config:
        from_attributes = True

class ExtractionResultBase(BaseModel):
    vendor_name: str = ""
    vendor_address: str = ""
    invoice_number: str = ""
    invoice_date: str = ""
    due_date: str = ""
    currency: str = "USD"
    subtotal: float = 0.0
    tax_amount: float = 0.0
    discount_amount: float = 0.0
    total_amount: float = 0.0
    detected_language: str = "English"

class ExtractionResultUpdate(ExtractionResultBase):
    line_items: Optional[List[LineItemBase]] = None

class ExtractionResultSchema(ExtractionResultBase):
    id: int
    document_id: int
    confidence_score: float
    confidence_status: str
    math_valid: bool
    is_duplicate: bool
    duplicate_of_id: Optional[int] = None
    extraction_provider: str
    created_at: datetime

    class Config:
        from_attributes = True

class DocumentSchema(BaseModel):
    id: int
    filename: str
    file_size: int
    mime_type: str
    status: str
    file_hash: str
    created_at: datetime
    updated_at: datetime
    extraction: Optional[ExtractionResultSchema] = None

    class Config:
        from_attributes = True

class DocumentDetailSchema(DocumentSchema):
    line_items: List[LineItemSchema] = []

class SpendAnalyticsSummary(BaseModel):
    total_documents: int
    total_spend: float
    avg_confidence: float
    currency: str = "USD"
    vendor_breakdown: List[Dict[str, Any]]
    category_breakdown: List[Dict[str, Any]]
    monthly_trend: List[Dict[str, Any]]

class WebhookTriggerRequest(BaseModel):
    webhook_url: Optional[str] = None
    document_id: int

class ManualVerificationRequest(BaseModel):
    extraction: ExtractionResultUpdate
    mark_verified: bool = True
