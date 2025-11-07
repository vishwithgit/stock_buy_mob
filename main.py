"""
Screener Order Analyzer
-----------------------

FastAPI service to analyze the latest order announcements on Screener.in.

- Fetches the last 15 announcements from your Screener search query.
- Extracts company names, order values, and announcement links.
- Fetches each company’s last-year sales data from Screener.
- Compares order values vs. sales and filters companies with large orders.
- Uses your Screener session cookie for authenticated scraping.

Author: Vishal (with ChatGPT)
"""

from fastapi import FastAPI, Query
import requests, re, os
from bs4 import BeautifulSoup
from typing import List, Dict, Optional

app = FastAPI(
    title="Screener Order Analyzer",
    description="Fetch order announcements and compare order value vs last-year revenue (authenticated).",
    version="2.0.0"
)

# -------------------------------
# Configuration
# -------------------------------

SESSION_ID = os.getenv("SCREENER_SESSION_ID")
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://www.screener.in/",
}
COOKIES = {"sessionid": SESSION_ID}

DEFAULT_QUERY = (
    "https://www.screener.in/full-text-search/?q=-%22Commissioner%22+-tax+-gst+"
    "%22order+received%22+or+%22award+of+order%22+or+%22Notification+of+Award%22+"
    "or+%22letter+of+intent%22+or+%22large+order%22+or+%22Order+for+Procurement%22+"
    "or+%22Awarding+of+order%22+or+%22bagged+an+order%22+or+%22Letter+of+Award%22+"
    "or+%22repeat+order%22+or+%22additional+order%22+or+%22Contract+Award%22"
)

# -------------------------------
# Helper Functions
# -------------------------------

def extract_number(text: str) -> Optional[float]:
    """Convert strings like ₹75 Cr, 2.3 million into float crores."""
    if not text:
        return None
    text = text.replace(",", "").lower()
    match = re.search(r'([\d\.]+)\s*(crore|cr|million|mn)?', text)
    if not match:
        return None
    num, unit = match.groups()
    num = float(num)
    if unit in ["million", "mn"]:
        num *= 0.1  # 1 million ≈ 0.1 crore
    return num


def extract_orders(query_url: str) -> List[Dict]:
    """Fetch Screener search results and extract recent 15 order announcements."""
    res = requests.get(query_url, headers=HEADERS, cookies=COOKIES)
    if res.status_code != 200:
        raise Exception(f"Failed to load Screener page: {res.status_code}")
    soup = BeautifulSoup(res.text, "html.parser")
    orders = []

    for card in soup.select(".media")[:15]:
        title_elem = card.select_one(".media-heading a")
        if not title_elem:
            continue
        company = title_elem.text.split(":")[0].strip()
        link = "https://www.screener.in" + title_elem["href"]
        text = card.get_text(" ", strip=True)
        order_val_match = re.search(r'₹\s?([\d,\.]+)\s?(crore|cr|million|mn)?', text, re.I)
        order_val_text = order_val_match.group(0) if order_val_match else None

        orders.append({
            "company": company,
            "order_value": order_val_text,
            "link": link
        })
    return orders


def get_revenue(company_slug: str) -> Optional[float]:
    """Fetch last year total revenue from company Screener page."""
    url = f"https://www.screener.in/company/{company_slug}/"
    res = requests.get(url, headers=HEADERS, cookies=COOKIES)
    if res.status_code != 200:
        return None
    soup = BeautifulSoup(res.text, "html.parser")
    match = re.search(r'Total Revenue\s*([\d,]+)', soup.text)
    if match:
        try:
            return float(match.group(1).replace(",", ""))
        except:
            return None
    return None

# -------------------------------
# API Routes
# -------------------------------

@app.get("/")
def root():
    """Check API health and login status."""
    return {
        "status": "OK ✅",
        "login_enabled": bool(SESSION_ID),
        "message": "Screener Order Analyzer API running."
    }


@app.get("/analyze")
def analyze(query: str = Query(DEFAULT_QUERY)):
    """
    Scrape Screener orders (using login cookie),
    compare order values vs last year's revenue,
    and return companies where order ≥ sales.
    """
    if not SESSION_ID:
        return {"error": "Missing SCREENER_SESSION_ID. Please set it in environment variables."}

    try:
        orders = extract_orders(query)
    except Exception as e:
        return {"error": f"Failed to fetch Screener data: {e}"}

    results = []

    for order in orders:
        company_slug = order["company"].split()[0]
        revenue = get_revenue(company_slug)
        order_val_num = extract_number(order["order_value"])
        if not revenue or not order_val_num:
            continue

        order_value_rupees = order_val_num * 1e7  # crore → rupees
        ratio = order_value_rupees / revenue if revenue else 0

        if ratio >= 1:
            results.append({
                "company": order["company"],
                "order_value": order["order_value"],
                "sales_last_year": f"₹{revenue:,.0f}",
                "ratio": round(ratio, 2),
                "link": order["link"]
            })

    return {
        "total_orders_checked": len(orders),
        "companies_with_high_order_ratio": len(results),
        "filtered_companies": results
    }
