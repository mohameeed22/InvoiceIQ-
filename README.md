# InvoiceIQ 📑⚡
### AI-Powered Invoice & Receipt Data Extraction API & Review Dashboard

**InvoiceIQ** is an AI document intelligence API and web dashboard that converts unstructured invoices and receipts (PDFs, scans, and phone photos) into structured, validated JSON data in seconds.

Designed specifically to handle real-world messiness — skewed photos, non-English documents, handwritten notes, and variable vendor formats — InvoiceIQ combines **OpenCV computer vision preprocessing** with **Vision LLMs** (Groq, OpenAI, Gemini) and a **mathematical validation & confidence engine**.

---

## Key Features

- 📸 **Multi-Format Ingestion**: Accepts PDFs, scanned images, phone photos (PNG, JPG, WEBP).
- 🧹 **Computer Vision Preprocessing**: Automatic deskewing, denoising, and contrast normalization using OpenCV and Pillow.
- 🧠 **Vision LLM Extraction Engine**: Powered by Groq Vision (`llama-3.2-vision`), OpenAI (`gpt-4o-mini`), or Gemini, with a built-in **Intelligent Demo Extractor** for zero-config instant evaluation.
- ⚖️ **Validation & Confidence Scoring**: Performs mathematical cross-checks ($\text{Subtotal} + \text{Tax} = \text{Total}$, line-items sum check) and flags low-confidence files ($0-100\%$).
- 🏷️ **Line-Item Auto-Categorization**: Auto-tags expenses into categories (*Software & Subscriptions*, *Office Supplies*, *Travel & Dining*, *Utilities*, *Professional Services*).
- 👯 **Duplicate Detection**: SHA-256 document hashing + vendor invoice number deduplication.
- 📊 **Spend Analytics Dashboard**: Real-time visual graphs for vendor spend breakdown and expense categories.
- 🔌 **Export & Webhook Integrations**: Instant CSV/JSON downloads, QuickBooks API payload formatting, and automated **n8n / Zapier webhook dispatch**.

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Backend API** | FastAPI (Python 3.13) |
| **Database** | SQLite / PostgreSQL (SQLAlchemy ORM) |
| **Vision AI** | Groq Vision / OpenAI / Gemini / Fallback Synthesizer |
| **Preprocessing** | OpenCV, Pillow, NumPy |
| **Frontend UI** | Modern HTML5, Vanilla CSS Design System, JavaScript, Chart.js, Lucide Icons |
| **Automation** | Webhook Dispatcher (n8n / Zapier / QuickBooks payload) |

---

## System Architecture

```
Client Upload (PDF / PNG / JPG)
          ↓
  FastAPI Endpoint (/api/v1/documents/upload)
          ↓
  Computer Vision Preprocessing (Deskewing / Denoise / Normalize)
          ↓
  Vision LLM (Groq / OpenAI / Gemini / Intelligent Engine)
          ↓
  Validation Layer (Math verification + Confidence score 0-100%)
          ↓
  Expense Categorization & Duplicate Hashing
          ↓
  Database (Document, Extraction, LineItems, AuditLog)
          ↓
  Review Dashboard & n8n / QuickBooks Webhook Sync
```

---

## Quick Start Guide

### 1. Installation
```bash
# Clone repository
cd InvoiceIQ

# Activate Virtual Environment (or create py -m venv venv)
.\venv\Scripts\activate

# Install requirements
pip install -r backend/requirements.txt
```

### 2. Seed Sample Data (Optional)
```bash
.\venv\Scripts\python.exe scripts/seed_data.py
```

### 3. Launch Server
```bash
.\venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

- 🌐 **Web Dashboard**: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- 📖 **Interactive API Documentation (Swagger)**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## API Endpoints Overview

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/documents/upload` | Upload single or batch invoices/receipts for extraction |
| `GET` | `/api/v1/documents` | List uploaded documents with status and confidence score |
| `GET` | `/api/v1/documents/{id}` | Retrieve document details, extracted JSON, & line items |
| `PUT` | `/api/v1/documents/{id}/verify` | Update manually corrected fields & line items |
| `DELETE` | `/api/v1/documents/{id}` | Delete document and associated records |
| `GET` | `/api/v1/documents/{id}/export/csv` | Download CSV formatted export |
| `GET` | `/api/v1/documents/{id}/export/json` | Download QuickBooks-compatible JSON payload |
| `POST` | `/api/v1/documents/{id}/export/webhook` | Dispatch payload to n8n / Zapier webhook endpoint |
| `GET` | `/api/v1/analytics/summary` | Retrieve total spend, vendor breakdown, & category analytics |

---

## Upwork Portfolio Tagline & Pitch

> **InvoiceIQ** — An AI-powered API that turns messy invoices and receipts into clean, structured data in seconds, with built-in validation, multi-language support, and direct sync to Google Sheets, Airtable, and QuickBooks.
