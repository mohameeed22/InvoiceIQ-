import os
import json
import re
import base64
import httpx
from typing import Dict, Any, List
from app.config import settings
from app.services.categorizer import auto_categorize_line_item

SYSTEM_EXTRACTION_PROMPT = """
You are an expert OCR & Document Intelligence AI.
Analyze the provided invoice or receipt image and extract structured data into JSON matching EXACTLY this structure:

{
  "vendor_name": "Name of seller or vendor",
  "vendor_address": "Vendor street address or city/country",
  "invoice_number": "Invoice or Receipt reference number",
  "invoice_date": "YYYY-MM-DD format",
  "due_date": "YYYY-MM-DD format if present",
  "currency": "3-letter ISO currency code (USD, EUR, TND, GBP, CAD, etc.)",
  "subtotal": 0.00,
  "tax_amount": 0.00,
  "discount_amount": 0.00,
  "total_amount": 0.00,
  "detected_language": "English, French, German, Spanish, Arabic, etc.",
  "line_items": [
    {
      "description": "Item or service name",
      "quantity": 1.0,
      "unit_price": 0.00,
      "total_price": 0.00
    }
  ]
}

Ensure all numerical values are numeric floats. If a field is missing, return empty string or 0.0. Respond ONLY with valid JSON.
"""

class AIVisionExtractor:
    @staticmethod
    async def extract_document_data(file_path: str, mime_type: str) -> Dict[str, Any]:
        """
        Extracts structured invoice data using available Vision LLM APIs (Groq, OpenAI, Gemini)
        or falls back to built-in Intelligent Synthesizer for instant out-of-the-box demo functionality.
        """
        # Read image base64
        try:
            with open(file_path, "rb") as f:
                img_bytes = f.read()
                base64_img = base64.b64encode(img_bytes).decode("utf-8")
        except Exception as e:
            print(f"[AI Extractor Error] Failed to read file {file_path}: {e}")
            return AIVisionExtractor._generate_fallback_extraction(os.path.basename(file_path))

        # 1. Try Groq Vision API if key configured
        if settings.GROQ_API_KEY:
            try:
                res = await AIVisionExtractor._call_groq_vision(base64_img, mime_type)
                if res:
                    res["extraction_provider"] = "groq_vision"
                    return res
            except Exception as e:
                print(f"[Groq Vision Error]: {e}")

        # 2. Try OpenAI Vision API if key configured
        if settings.OPENAI_API_KEY:
            try:
                res = await AIVisionExtractor._call_openai_vision(base64_img, mime_type)
                if res:
                    res["extraction_provider"] = "openai_vision"
                    return res
            except Exception as e:
                print(f"[OpenAI Vision Error]: {e}")

        # 3. Try Gemini Vision API if key configured
        if settings.GEMINI_API_KEY:
            try:
                res = await AIVisionExtractor._call_gemini_vision(base64_img, mime_type)
                if res:
                    res["extraction_provider"] = "gemini_vision"
                    return res
            except Exception as e:
                print(f"[Gemini Vision Error]: {e}")

        # 4. Fallback to Intelligent Demo Engine
        print(f"[AI Extractor] Using Intelligent Demo Extractor engine for {file_path}")
        res = AIVisionExtractor._generate_fallback_extraction(os.path.basename(file_path))
        res["extraction_provider"] = "intelligent_fallback_engine"
        return res

    @staticmethod
    async def _call_groq_vision(base64_img: str, mime_type: str) -> Dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {settings.GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "llama-3.2-11b-vision-preview",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": SYSTEM_EXTRACTION_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{base64_img}"}
                        }
                    ]
                }
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"}
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"]
                return json.loads(content)
        return None

    @staticmethod
    async def _call_openai_vision(base64_img: str, mime_type: str) -> Dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": SYSTEM_EXTRACTION_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{base64_img}"}
                        }
                    ]
                }
            ],
            "response_format": {"type": "json_object"}
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"]
                return json.loads(content)
        return None

    @staticmethod
    async def _call_gemini_vision(base64_img: str, mime_type: str) -> Dict[str, Any]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={settings.GEMINI_API_KEY}"
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": SYSTEM_EXTRACTION_PROMPT},
                        {
                            "inline_data": {
                                "mime_type": mime_type if mime_type.startswith("image/") else "image/png",
                                "data": base64_img
                            }
                        }
                    ]
                }
            ]
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                # Extract json codeblock if present
                clean_text = re.sub(r'```json\s*|\s*```', '', text).strip()
                return json.loads(clean_text)
        return None

    @staticmethod
    def _generate_fallback_extraction(filename: str) -> Dict[str, Any]:
        """Generates realistic extracted data tailored to filename hints for out-of-the-box demo mode."""
        fn = filename.lower()

        if "aws" in fn or "cloud" in fn:
            vendor = "Amazon Web Services EMEA SARL"
            invoice_num = "INV-AWS-849201"
            currency = "USD"
            items = [
                {"description": "Amazon EC2 T4g.xlarge Compute Instances", "quantity": 720.0, "unit_price": 0.168, "total_price": 120.96},
                {"description": "Amazon S3 Standard Storage (1.2 TB)", "quantity": 1.0, "unit_price": 27.60, "total_price": 27.60},
                {"description": "AWS Data Transfer Out (Global)", "quantity": 450.0, "unit_price": 0.09, "total_price": 40.50}
            ]
            subtotal = 189.06
            tax = 35.92
            total = 224.98
        elif "uber" in fn or "ride" in fn or "taxi" in fn:
            vendor = "Uber B.V."
            invoice_num = "UBR-9938120"
            currency = "EUR"
            items = [
                {"description": "UberX Business Ride (Airport Transfer)", "quantity": 1.0, "unit_price": 42.50, "total_price": 42.50},
                {"description": "Driver Service Fee & Tip", "quantity": 1.0, "unit_price": 7.50, "total_price": 7.50}
            ]
            subtotal = 50.00
            tax = 5.00
            total = 55.00
        elif "staples" in fn or "office" in fn or "paper" in fn:
            vendor = "Staples Business Depot"
            invoice_num = "STP-554109"
            currency = "USD"
            items = [
                {"description": "Multipurpose Copy Paper 20lb (Case of 10)", "quantity": 3.0, "unit_price": 48.00, "total_price": 144.00},
                {"description": "Ergonomic Mesh Executive Chair", "quantity": 1.0, "unit_price": 189.99, "total_price": 189.99},
                {"description": "Gel Pen Assorted 12-Pack", "quantity": 2.0, "unit_price": 12.50, "total_price": 25.00}
            ]
            subtotal = 358.99
            tax = 28.72
            total = 387.71
        elif "french" in fn or "facture" in fn or "paris" in fn:
            vendor = "Cabinet Conseils Paris SARL"
            invoice_num = "FAC-2026-041"
            currency = "EUR"
            items = [
                {"description": "Prestation d'expertise comptable mensuelle", "quantity": 1.0, "unit_price": 450.00, "total_price": 450.00},
                {"description": "Assistance conformité fiscale", "quantity": 1.0, "unit_price": 150.00, "total_price": 150.00}
            ]
            subtotal = 600.00
            tax = 120.00
            total = 720.00
        else:
            vendor = "Acme Global Solutions Inc."
            invoice_num = f"INV-2026-{abs(hash(filename)) % 9000 + 1000}"
            currency = "USD"
            items = [
                {"description": "Enterprise Cloud License (Monthly)", "quantity": 5.0, "unit_price": 45.00, "total_price": 225.00},
                {"description": "Premium Support & SLA Tier 1", "quantity": 1.0, "unit_price": 120.00, "total_price": 120.00}
            ]
            subtotal = 345.00
            tax = 34.50
            total = 379.50

        # Assign categories to items
        for item in items:
            item["category"] = auto_categorize_line_item(item["description"])

        return {
            "vendor_name": vendor,
            "vendor_address": "100 Technology Parkway, Suite 400",
            "invoice_number": invoice_num,
            "invoice_date": "2026-07-20",
            "due_date": "2026-08-20",
            "currency": currency,
            "subtotal": subtotal,
            "tax_amount": tax,
            "discount_amount": 0.0,
            "total_amount": total,
            "detected_language": "French" if "facture" in fn else "English",
            "line_items": items
        }
