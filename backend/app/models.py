from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.database import Base

class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_hash = Column(String(64), index=True, nullable=False)
    file_size = Column(Integer, nullable=False)
    mime_type = Column(String(100), nullable=False)
    status = Column(String(50), default="uploaded")  # uploaded, processing, extracted, verified, error
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    extraction = relationship("ExtractionResult", back_populates="document", uselist=False, cascade="all, delete-orphan")
    line_items = relationship("LineItem", back_populates="document", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="document", cascade="all, delete-orphan")

class ExtractionResult(Base):
    __tablename__ = "extraction_results"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True)
    
    vendor_name = Column(String(255), default="")
    vendor_address = Column(String(500), default="")
    invoice_number = Column(String(100), default="")
    invoice_date = Column(String(50), default="")
    due_date = Column(String(50), default="")
    currency = Column(String(10), default="USD")
    
    subtotal = Column(Float, default=0.0)
    tax_amount = Column(Float, default=0.0)
    discount_amount = Column(Float, default=0.0)
    total_amount = Column(Float, default=0.0)
    
    detected_language = Column(String(50), default="English")
    confidence_score = Column(Float, default=0.0)  # 0.0 to 100.0
    confidence_status = Column(String(50), default="NEEDS_REVIEW")  # HIGH, NEEDS_REVIEW, FLAG
    math_valid = Column(Boolean, default=True)
    is_duplicate = Column(Boolean, default=False)
    duplicate_of_id = Column(Integer, nullable=True)
    
    raw_json = Column(Text, default="{}")
    extraction_provider = Column(String(50), default="mock")
    created_at = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document", back_populates="extraction")

class LineItem(Base):
    __tablename__ = "line_items"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    
    description = Column(String(500), nullable=False)
    quantity = Column(Float, default=1.0)
    unit_price = Column(Float, default=0.0)
    total_price = Column(Float, default=0.0)
    category = Column(String(100), default="General Expense")

    document = relationship("Document", back_populates="line_items")

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    action = Column(String(100), nullable=False)
    details = Column(Text, default="")
    timestamp = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document", back_populates="audit_logs")
