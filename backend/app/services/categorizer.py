import re

CATEGORY_MAPPING = {
    "Software & Subscriptions": [
        "software", "subscription", "license", "saas", "github", "aws", "google cloud", 
        "azure", "slack", "zoom", "figma", "notion", "adobe", "domain", "hosting", 
        "chatgpt", "openai", "api", "cloud"
    ],
    "Office Supplies & Hardware": [
        "paper", "pen", "desk", "chair", "laptop", "monitor", "keyboard", "mouse", 
        "cable", "hardware", "printer", "ink", "stapler", "notebook", "office"
    ],
    "Travel & Dining": [
        "hotel", "flight", "airline", "uber", "lyft", "taxi", "train", "restaurant", 
        "cafe", "coffee", "lunch", "dinner", "meal", "food", "parking", "fuel", "gas"
    ],
    "Utilities & Infrastructure": [
        "electricity", "water", "internet", "fiber", "phone", "telecom", "utility", 
        "broadband", "mobile"
    ],
    "Professional Services": [
        "consulting", "legal", "accounting", "audit", "design", "marketing", 
        "freelance", "advisory", "agency", "retainer"
    ]
}

def auto_categorize_line_item(description: str) -> str:
    """Auto-tags expense items based on description keyword matching."""
    if not description:
        return "General Expense"

    desc_lower = description.lower()

    for category, keywords in CATEGORY_MAPPING.items():
        for kw in keywords:
            if re.search(r'\b' + re.escape(kw) + r'\b', desc_lower):
                return category

    return "General Expense"
