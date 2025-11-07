from fastapi import FastAPI, Query
import requests, re, pandas as pd
from bs4 import BeautifulSoup

app = FastAPI()

HEADERS = {"User-Agent": "Mozilla/5.0"}

DEFAULT_QUERY = "https://www.screener.in/full-text-search/?q=-%22Commissioner%22+-tax+-gst+%22order+received%22+or+%22award+of+order%22+or+%22Notification+of+Award%22+or+%22letter+of+intent%22+or+%22large+order%22+or+%22Order+for+Procurement%22+or+%22Awarding+of+order%22+or+%22bagged+an+order%22+or+%22Letter+of+Award%22+or+%22repeat+order%22+or+%22additional+order%22+or+%22Contract+Award%22"

def extract_number(text):
    """Convert Indian-formatted numbers like ₹75 Cr, 2.3 million into float crores."""
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

def extract_orders(query_url=DEFAULT_QUERY):
    res = requests.get(query_url, headers=HEADERS)
    soup = BeautifulSoup(res.text, "html.parser")
    orders = []

    for card in soup.select(".media")[:15]:
        title_elem = card.select_one(".media-heading a")
        if not title_elem:
            continue
        company = title_elem.text.split(":")[0].strip()
        link = "https://www.screener.in" + title_elem["href"]
        text = card.get_text(" ", strip=True)
        order_val = re.search(r'₹\s?([\d,\.]+)\s?(crore|cr|million|mn)?', text, re.I)
        order_val_text = order_val.group(0) if order_val else None
        orders.append({"company": company, "order_value": order_val_text, "link": link})
    return orders

def get_revenue(company_slug):
    url = f"https://www.screener.in/company/{company_slug}/"
    res = requests.get(url, headers=HEADERS)
    soup = BeautifulSoup(res.text, "html.parser")
    match = re.search(r'Total Revenue\s*([\d,]+)', soup.text)
    if match:
        return float(match.group(1).replace(",", ""))
    return None

@app.get("/")
def root():
    return {"message": "Screener Order Analyzer API running ✅"}

@app.get("/analyze")
def analyze(query: str = Query(DEFAULT_QUERY)):
    orders = extract_orders(query)
    results = []

    for order in orders:
        company_slug = order["company"].split()[0]  # crude guess
        revenue = get_revenue(company_slug)
        order_val_num = extract_number(order["order_value"])
        if not revenue or not order_val_num:
            continue
        ratio = order_val_num * 1e7 / revenue if revenue else 0  # ₹ crore → ₹ value
        if ratio >= 1:
            results.append({
                "company": order["company"],
                "order_value": order["order_value"],
                "sales_last_year": f"₹{revenue:,}",
                "ratio": round(ratio, 2),
                "link": order["link"]
            })
    
    return {"count": len(results), "filtered_companies": results}
