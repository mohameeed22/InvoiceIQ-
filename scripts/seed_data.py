import os
import sys
from PIL import Image, ImageDraw, ImageFont

# Add backend directory to sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.database import SessionLocal, Base, engine
from app.models import Document, ExtractionResult, LineItem, AuditLog
from app.config import settings
from app.services.validator import compute_file_hash

def create_sample_receipt_image(filepath: str, title: str, inv_no: str, total_str: str):
    """Creates a realistic synthetic receipt image for testing & visual preview."""
    img = Image.new('RGB', (600, 800), color=(250, 250, 248))
    draw = ImageDraw.Draw(img)
    
    # Draw border & header
    draw.rectangle([20, 20, 580, 780], outline=(200, 200, 200), width=2)
    draw.text((200, 50), title.upper(), fill=(20, 30, 50))
    draw.text((200, 80), "123 Business Avenue, Suite 100", fill=(100, 100, 100))
    draw.text((200, 100), f"INVOICE #: {inv_no}", fill=(50, 50, 50))
    draw.text((200, 120), "DATE: 2026-07-25", fill=(50, 50, 50))

    draw.line([40, 160, 560, 160], fill=(180, 180, 180), width=2)

    # Items table header
    draw.text((40, 180), "DESCRIPTION", fill=(80, 80, 80))
    draw.text((400, 180), "QTY", fill=(80, 80, 80))
    draw.text((480, 180), "TOTAL", fill=(80, 80, 80))
    draw.line([40, 200, 560, 200], fill=(220, 220, 220), width=1)

    # Table rows
    y = 220
    items = [
        ("Cloud Server Hosting (Monthly)", "1", "$120.00"),
        ("SSL Certificate Renewal", "2", "$40.00"),
        ("Database Backup Storage", "1", "$25.00"),
        ("Technical Support Tier 2", "3", "$150.00")
    ]
    for desc, qty, amt in items:
        draw.text((40, y), desc, fill=(30, 30, 30))
        draw.text((410, y), qty, fill=(30, 30, 30))
        draw.text((480, y), amt, fill=(30, 30, 30))
        y += 40

    draw.line([40, y + 10, 560, y + 10], fill=(180, 180, 180), width=2)

    # Summary
    draw.text((320, y + 30), "SUBTOTAL:", fill=(50, 50, 50))
    draw.text((480, y + 30), "$335.00", fill=(50, 50, 50))
    draw.text((320, y + 60), "TAX (10%):", fill=(50, 50, 50))
    draw.text((480, y + 60), "$33.50", fill=(50, 50, 50))

    draw.line([320, y + 90, 560, y + 90], fill=(40, 40, 40), width=2)
    draw.text((320, y + 100), "GRAND TOTAL:", fill=(10, 20, 40))
    draw.text((480, y + 100), total_str, fill=(10, 120, 60))

    img.save(filepath)

def seed_database():
    """Populates database with initial sample documents for demo."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    if db.query(Document).count() > 0:
        print("[Seed] Database already contains records. Skipping seed.")
        db.close()
        return

    print("[Seed] Generating sample document images & pre-populating database...")

    samples = [
        {
            "filename": "aws_monthly_invoice.png",
            "vendor": "Amazon Web Services EMEA SARL",
            "vendor_addr": "38 Avenue John F. Kennedy, L-1855 Luxembourg",
            "inv_num": "AWS-2026-90412",
            "date": "2026-07-15",
            "due_date": "2026-08-15",
            "currency": "USD",
            "subtotal": 315.00,
            "tax": 31.50,
            "total": 346.50,
            "confidence": 98.5,
            "status": "HIGH",
            "items": [
                ("Amazon EC2 Linux Instances (t4g.large)", 2.0, 110.00, 220.00, "Software & Subscriptions"),
                ("Amazon S3 Standard Storage (500GB)", 1.0, 25.00, 25.00, "Software & Subscriptions"),
                ("AWS CloudWatch Monitoring", 1.0, 70.00, 70.00, "Utilities & Infrastructure")
            ]
        },
        {
            "filename": "uber_business_receipt.png",
            "vendor": "Uber Technologies Inc.",
            "vendor_addr": "1515 3rd St, San Francisco, CA 94158",
            "inv_num": "UBR-7740219",
            "date": "2026-07-22",
            "due_date": "2026-07-22",
            "currency": "EUR",
            "subtotal": 48.00,
            "tax": 4.80,
            "total": 52.80,
            "confidence": 94.0,
            "status": "HIGH",
            "items": [
                ("Uber Comfort Airport Ride", 1.0, 48.00, 48.00, "Travel & Dining")
            ]
        },
        {
            "filename": "staples_office_supplies.png",
            "vendor": "Staples Office Solutions",
            "vendor_addr": "500 Staples Drive, Framingham, MA",
            "inv_num": "STP-991204",
            "date": "2026-07-18",
            "due_date": "2026-08-18",
            "currency": "USD",
            "subtotal": 185.00,
            "tax": 14.80,
            "total": 199.80,
            "confidence": 72.0,
            "status": "NEEDS_REVIEW",
            "items": [
                ("Ergonomic Mesh Chair Cushion", 2.0, 45.00, 90.00, "Office Supplies & Hardware"),
                ("Highlighter 10-Pack & Sticky Notes", 5.0, 19.00, 95.00, "Office Supplies & Hardware")
            ]
        }
    ]

    for s in samples:
        file_path = os.path.join(settings.UPLOAD_DIR, s["filename"])
        create_sample_receipt_image(file_path, s["vendor"], s["inv_num"], f"${s['total']:.2f}")

        file_hash = compute_file_hash(file_path)
        file_size = os.path.getsize(file_path)

        doc = Document(
            filename=s["filename"],
            file_path=file_path,
            file_hash=file_hash,
            file_size=file_size,
            mime_type="image/png",
            status="extracted"
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

        ext = ExtractionResult(
            document_id=doc.id,
            vendor_name=s["vendor"],
            vendor_address=s["vendor_addr"],
            invoice_number=s["inv_num"],
            invoice_date=s["date"],
            due_date=s["due_date"],
            currency=s["currency"],
            subtotal=s["subtotal"],
            tax_amount=s["tax"],
            discount_amount=0.0,
            total_amount=s["total"],
            detected_language="English",
            confidence_score=s["confidence"],
            confidence_status=s["status"],
            math_valid=True,
            is_duplicate=False,
            extraction_provider="seed_demo"
        )
        db.add(ext)

        for name, qty, price, tot, cat in s["items"]:
            li = LineItem(
                document_id=doc.id,
                description=name,
                quantity=qty,
                unit_price=price,
                total_price=tot,
                category=cat
            )
            db.add(li)

        audit = AuditLog(
            document_id=doc.id,
            action="SEEDED",
            details="Pre-seeded demo document."
        )
        db.add(audit)

    db.commit()
    db.close()
    print("[Seed] Seeding completed successfully!")

if __name__ == "__main__":
    seed_database()
