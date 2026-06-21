import os
import re
import csv
import io
import json
import xml.etree.ElementTree as ET
from datetime import datetime, date

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, request, Response
from flask_cors import CORS

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app = Flask(__name__, static_folder=os.path.join(project_root, 'static'), static_url_path='')
CORS(app)

# ─── helpers ──────────────────────────────────────────────────────────────

FED_BASE = "https://www.federalreserve.gov"
FOMC_CALENDAR_URL = f"{FED_BASE}/monetarypolicy/fomccalendars.htm"
ECB_URL = "https://www.ecb.europa.eu/stats/policy_and_exchange_rates/key_ecb_interest_rates/html/index.en.html"
BOE_URL = "https://www.bankofengland.co.uk/boeapps/iadb/Repo.asp"
TE_BASE = "https://tradingeconomics.com"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

MONTH_NAMES = {
    "January": 1, "February": 2, "March": 3, "April": 4,
    "May": 5, "June": 6, "July": 7, "August": 8,
    "September": 9, "October": 10, "November": 11, "December": 12
}

def safe_float(v):
    try:
        return float(v)
    except (ValueError, TypeError):
        return None

def safe_int(v):
    try:
        return int(v)
    except (ValueError, TypeError):
        return None

def parse_fed_fraction(s):
    """Convert Fed fraction notation like '3-1/2' to 3.5"""
    s = s.strip()
    if "/" in s:
        parts = s.split("-") if "-" in s else ["0", s]
        if len(parts) == 2:
            whole = safe_float(parts[0]) if parts[0] else 0
            frac_parts = parts[1].split("/")
            if len(frac_parts) == 2:
                num = safe_float(frac_parts[0])
                den = safe_float(frac_parts[1])
                if num is not None and den and den > 0:
                    return whole + num / den
    return safe_float(s)


# ─── FOMC Calendar scraper ────────────────────────────────────────────────

def scrape_fomc_calendar():
    resp = requests.get(FOMC_CALENDAR_URL, headers=HEADERS, timeout=15)
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")
    meetings = []

    # Find all FOMC meeting rows
    meeting_divs = soup.select("div.fomc-meeting, div.fomc-meeting--shaded")
    if not meeting_divs:
        meeting_divs = soup.find_all("div", class_=re.compile(r"fomc-meeting"))

    for div in meeting_divs:
        # Determine year from preceding h4
        year = None
        prev = div.find_previous(["h4", "h3", "h2"])
        while prev:
            m = re.search(r"(20\d{2})\s+FOMC", prev.get_text())
            if m:
                year = int(m.group(1))
                break
            prev = prev.find_previous(["h4", "h3", "h2"])
        if not year:
            continue

        month_el = div.select_one(".fomc-meeting__month, .fomc-meeting--shaded__month")
        date_el = div.select_one(".fomc-meeting__date")

        if not month_el or not date_el:
            continue

        month_name = month_el.get_text(strip=True)
        days_raw = date_el.get_text(strip=True)

        month_num = MONTH_NAMES.get(month_name)
        if not month_num:
            continue

        has_sep = "*" in days_raw or "Projection Materials" in div.get_text()
        has_press = "Press Conference" in div.get_text()
        days_clean = days_raw.replace("*", "").strip()
        parts = days_clean.split("-")
        day_str = parts[-1].strip() if parts else days_clean.strip()

        if not day_str.isdigit():
            continue

        try:
            parsed = date(year, month_num, int(day_str))
            meetings.append({
                "year": year,
                "month": month_name,
                "days": days_clean,
                "dateDisplay": f"{month_name} {days_clean}, {year}",
                "sep": has_sep,
                "pressConference": has_press,
                "parsedDate": parsed.isoformat()
            })
        except (ValueError, TypeError):
            pass

    meetings.sort(key=lambda m: m["parsedDate"] or "")
    return meetings


# ─── /api/meetings ────────────────────────────────────────────────────────

@app.route("/api/meetings")
def get_meetings():
    try:
        meetings = scrape_fomc_calendar()
        return jsonify(meetings)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── /api/meetings/csv ────────────────────────────────────────────────────

@app.route("/api/meetings/csv")
def meetings_csv():
    try:
        meetings = scrape_fomc_calendar()
    except Exception as e:
        return str(e), 500

    year = request.args.get("year")
    if year:
        meetings = [m for m in meetings if str(m["year"]) == str(year)]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Year", "Month", "Days", "Date Display", "SEP", "Press Conference"])
    for m in meetings:
        writer.writerow([
            m["year"], m["month"], m["days"],
            m["dateDisplay"],
            "Yes" if m["sep"] else "No",
            "Yes" if m["pressConference"] else "No"
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename=meetings_{year or 'all'}.csv"}
    )


# ─── /api/sep ─────────────────────────────────────────────────────────────

HISTORICAL_2025 = {
    "gdp": {"Q4": 2.5},
    "unemployment": {"Q4": 4.2},
    "pce": {"Q4": 2.5},
    "corePce": {"Q4": 2.7}
}

def parse_sep_html(html):
    soup = BeautifulSoup(html, "html.parser")
    result = {"dotPlot": [], "gdp": {}, "unemployment": {}, "pce": {}, "corePce": {}, "historical2025": HISTORICAL_2025}

    tables = soup.find_all("table")
    year_cols = ["2026", "2027", "2028", "Longer run"]

    for table in tables:
        text = table.get_text(" ", strip=True)

        # ── Dot plot table ──
        if "Midpoint of target range" in text or "Federal funds rate" in text:
            rows = table.find_all("tr")
            dots = []
            for row in rows:
                th = row.find("th", class_="stub")
                if not th:
                    continue
                rate_val = safe_float(th.get_text(strip=True))
                if rate_val is None:
                    continue
                tds = row.find_all("td")
                entry = {"rate": rate_val}
                for idx, col in enumerate(year_cols):
                    if idx < len(tds):
                        td = tds[idx]
                        # Only count data cells (non-empty)
                        if "emptydata" not in td.get("class", []) and td.get_text(strip=True):
                            cnt = safe_int(td.get_text(strip=True))
                            if cnt is not None:
                                entry[col] = cnt
                dots.append(entry)
            if dots:
                result["dotPlot"] = dots

        # ── Economic projection table ──
        if "Change in real GDP" in text:
            rows = table.find_all("tr")
            current_var = None
            for i, row in enumerate(rows):
                cells = row.find_all(["td", "th"])
                texts = [c.get_text(strip=True) for c in cells]
                if not texts:
                    continue
                label = texts[0].lower()

                def parse_vals(ts):
                    entry = {}
                    for idx, col in enumerate(year_cols):
                        if idx < len(ts):
                            fv = safe_float(ts[idx])
                            if fv is not None:
                                entry[col] = fv
                    return entry

                vals = texts[1:5]
                entry = parse_vals(vals)

                if "change in real gdp" in label:
                    current_var = "gdp"
                    if entry: result["gdp"] = entry
                elif "unemployment rate" in label and "projection" not in label:
                    current_var = "unemployment"
                    if entry: result["unemployment"] = entry
                elif "pce inflation" in label and "core" not in label and "projection" not in label:
                    current_var = "pce"
                    if entry: result["pce"] = entry
                elif "core pce" in label and "projection" not in label and entry:
                    current_var = "corePce"
                    if entry: result["corePce"] = entry
                elif "projection" in label or "previous" in label:
                    # Previous median row
                    pkey = f"{current_var}Prev" if current_var else None
                    if pkey and entry:
                        result[pkey] = entry
                else:
                    current_var = None

    return result

@app.route("/api/sep")
def get_sep():
    date_param = request.args.get("date", "")
    url = f"{FED_BASE}/monetarypolicy/fomcprojtabl{date_param}.htm" if date_param else None

    if url is None:
        try:
            meetings = scrape_fomc_calendar()
        except Exception as e:
            return jsonify({"error": str(e)}), 500

        today = date.today()
        sep_meetings = [m for m in meetings if m.get("sep") and m["parsedDate"] and date.fromisoformat(m["parsedDate"]) <= today]
        if not sep_meetings:
            return jsonify({"error": "No SEP meeting found"}), 404

        latest = sep_meetings[-1]
        m = MONTH_NAMES.get(latest.get("month", ""))
        y = latest.get("year")
        day_str = str(latest.get("days", ""))
        # Take the last day if range
        d_part = day_str.split("-")[-1].strip() if "-" in day_str else day_str.strip()
        if not (m and y and d_part.isdigit()):
            return jsonify({"error": "Cannot determine SEP date"}), 400
        date_str = f"{y}{m:02d}{int(d_part):02d}"
        url = f"{FED_BASE}/monetarypolicy/fomcprojtabl{date_str}.htm"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.encoding = "utf-8"
        html = resp.text
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    result = parse_sep_html(html)
    result["source"] = url
    return jsonify(result)


# ─── /api/current-rate ────────────────────────────────────────────────────

@app.route("/api/current-rate")
def get_current_rate():
    try:
        meetings = scrape_fomc_calendar()
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    now = date.today()
    past = [m for m in meetings if m["parsedDate"] and date.fromisoformat(m["parsedDate"]) <= now]
    past.sort(key=lambda x: x["parsedDate"])
    if not past:
        return jsonify({"error": "No past meetings"}), 404

    latest = past[-1]
    y = latest["year"]
    month_num = MONTH_NAMES.get(latest["month"])
    day_str = str(latest["days"]).split("-")[-1].strip()
    if not (month_num and day_str.isdigit()):
        return jsonify({"error": "Cannot determine meeting date"}), 400
    d = int(day_str)
    date_str = f"{y}{month_num:02d}{d:02d}"

    # Try HTML statement page
    url = f"{FED_BASE}/newsevents/pressreleases/monetary{date_str}a.htm"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.encoding = "utf-8"
        text = resp.text
    except Exception:
        # Fallback to PDF
        url = f"{FED_BASE}/monetarypolicy/files/monetary{date_str}a1.pdf"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.encoding = "utf-8"
            text = resp.text
        except Exception:
            url = url.replace("a1.pdf", "a.pdf")
            try:
                resp = requests.get(url, headers=HEADERS, timeout=15)
                resp.encoding = "utf-8"
                text = resp.text
            except Exception as e:
                return jsonify({"error": str(e)}), 500

    # Parse rate from text (handles both decimal and fraction notation like "3-1/2 to 3-3/4")
    patterns = [
        r"federal funds rate at (.+?) to (.+?) percent",
        r"target range.*?rate at (.+?) to (.+?)(?: percent|\.)",
        r"([\d.]+)\s*to\s*([\d.]+)\s*percent",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
        if m:
            try:
                low_str = m.group(1).strip()
                high_str = m.group(2).strip()
                low = parse_fed_fraction(low_str)
                high = parse_fed_fraction(high_str)
                if low is not None and high is not None and low > 0:
                    mid = round((low + high) / 2, 2)
                    return jsonify({
                        "low": low, "high": high, "mid": mid,
                        "date": latest.get("dateDisplay", ""), "source": url
                    })
            except (ValueError, IndexError):
                pass

    return jsonify({
        "low": 4.25, "high": 4.50, "mid": 4.375,
        "date": latest.get("dateDisplay", ""),
        "note": "Used fallback value; could not parse statement text"
    })


# ─── /api/global-rates ────────────────────────────────────────────────────

def scrape_ecb_rate():
    try:
        resp = requests.get(ECB_URL, headers=HEADERS, timeout=15)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table", class_="table")
        if not table:
            table = soup.find("table")
        if not table:
            return 2.25, "up"
        rows = table.find_all("tr")
        rates = []
        for row in rows:
            cells = row.find_all("td")
            if len(cells) >= 3:
                val = cells[2].get_text(strip=True).replace("%", "").strip()
                fv = safe_float(val)
                if fv is not None:
                    rates.append(fv)
        if len(rates) >= 2:
            direction = "up" if rates[0] > rates[1] else "down" if rates[0] < rates[1] else "flat"
            return rates[0], direction
        if rates:
            return rates[0], "up"
        return 2.25, "up"
    except Exception:
        return 2.25, "up"


def scrape_boe_rate():
    rate = 3.75
    try:
        # Get current rate from the official Bank Rate history table
        resp = requests.get(BOE_URL, headers=HEADERS, timeout=15)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table", id="stats-table")
        if table:
            for row in table.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) >= 2:
                    fv = safe_float(cells[1].get_text(strip=True))
                    if fv is not None and 0 < fv < 20:
                        rate = fv
                        break
    except Exception:
        pass

    direction = "flat"
    try:
        # Determine direction from the latest decision page
        resp = requests.get(
            "https://www.bankofengland.co.uk/monetary-policy/the-interest-rate-bank-rate",
            headers=HEADERS, timeout=15
        )
        resp.encoding = "utf-8"
        text = resp.text
        if re.search(r"(?i)(?:increased|raised|hiked)\s+(?:to|by)", text):
            direction = "up"
        elif re.search(r"(?i)(?:decreased|cut|reduced|lowered)\s+(?:to|by)", text):
            direction = "down"
        elif re.search(r"(?i)(?:held|maintained|kept|unchanged|held\s+at|maintained\s+at)", text):
            direction = "flat"
    except Exception:
        pass

    return rate, direction


def scrape_tradingeconomics(country_code):
    try:
        url = f"{TE_BASE}/{country_code}/interest-rate"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        current = None
        previous = None

        # Try to find the primary "Interest Rate" (not deposit/interbank/etc) in Related table
        for tr in soup.find_all("tr"):
            cells = tr.find_all("td")
            if len(cells) < 3: continue
            name = cells[0].get_text(strip=True).lower()
            # Only match: exactly "interest rate" or ends with "interest rate" but not deposit/interbank
            if name == "interest rate" or (name.endswith("interest rate") and "deposit" not in name and "interbank" not in name):
                c1 = safe_float(cells[1].get_text(strip=True))
                c2 = safe_float(cells[2].get_text(strip=True))
                if c1 is not None and 0 < c1 < 20:
                    current = c1
                    previous = c2
                break

        # Fallback: search for Actual/Previous labels
        if current is None:
            for span in soup.find_all("span"):
                txt = span.get_text(strip=True).lower()
                if txt == "actual":
                    parent = span.parent
                    val_span = parent.find_next("span")
                    if val_span:
                        fv = safe_float(val_span.get_text(strip=True).replace("%",""))
                        if fv is not None and 0 < fv < 20:
                            current = fv
                if txt == "previous":
                    parent = span.parent
                    val_span = parent.find_next("span")
                    if val_span:
                        fv = safe_float(val_span.get_text(strip=True).replace("%",""))
                        if fv is not None and 0 < fv < 20:
                            previous = fv

        if current is None:
            return None, "up"

        direction = "up"
        if previous is not None:
            direction = "down" if current < previous else "up" if current > previous else "flat"
        return current, direction
    except Exception:
        return None, "up"


BANKS_CONFIG = [
    {"code": "Eurozone", "name": "European Central Bank", "country": "european-union", "next": "2026-07-23", "fallback": 2.25},
    {"code": "UK", "name": "Bank of England", "country": "united-kingdom", "next": "2026-07-30", "fallback": 3.75},
    {"code": "Japan", "name": "Bank of Japan", "country": "japan", "next": "2026-07-31", "fallback": 1.00},
    {"code": "Australia", "name": "Reserve Bank of Australia", "country": "australia", "next": "2026-08-11", "fallback": 4.35},
    {"code": "S.Korea", "name": "Bank of Korea", "country": "south-korea", "next": "2026-07-15", "fallback": 2.50},
    {"code": "Taiwan", "name": "Central Bank of Taiwan", "country": "taiwan", "next": "2026-09-17", "fallback": 2.00},
]

@app.route("/api/global-rates")
def get_global_rates():
    ecb_rate, ecb_dir = scrape_ecb_rate()
    boe_rate, boe_dir = scrape_boe_rate()

    results = []
    for bank in BANKS_CONFIG:
        rate = bank["fallback"]
        direction = "up"

        if bank["country"] == "european-union":
            rate, direction = ecb_rate, ecb_dir
        elif bank["country"] == "united-kingdom":
            rate, direction = boe_rate, boe_dir
        else:
            te_rate, te_dir = scrape_tradingeconomics(bank["country"])
            if te_rate is not None:
                rate, direction = te_rate, te_dir

        results.append({
            "code": bank["code"],
            "name": bank["name"],
            "rate": rate,
            "direction": direction,
            "nextMeeting": bank["next"]
        })

    return jsonify(results)


# ─── /api/news ────────────────────────────────────────────────────────────

RSS_FEEDS = [
    {"id": "Fed", "url": "https://www.federalreserve.gov/feeds/press_all.xml"},
    {"id": "ECB", "url": "https://www.ecb.europa.eu/rss/press.xml"},
    {"id": "BOE", "url": "https://www.bankofengland.co.uk/rss/news"},
    {"id": "BOJ", "url": "https://www.boj.or.jp/en/rss/whatsnew.xml"},
    {"id": "BOK", "url": "https://www.bok.or.kr/eng/bbs/E0000627/news.rss?menuNo=400022"},
]

def parse_rss_date(date_str):
    if not date_str:
        return None
    for fmt in [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
    ]:
        try:
            return datetime.strptime(date_str.strip(), fmt).strftime("%Y-%m-%d")
        except (ValueError, AttributeError):
            continue
    return date_str[:10] if date_str else None


IMPORTANT_KEYWORDS = {
    "Fed": [
        (100, ["fomc statement", "federal reserve issues fomc statement"]),
        (95,  ["economic projections", "release economic projections"]),
        (90,  ["minutes of the federal open market committee", "fomc minutes"]),
        (85,  ["monetary policy report", "semiannual monetary policy report", "discount rate"]),
        (80,  ["press conference", "takes oath of office", "chairman", "chair pro tempore", "resignation"]),
        (75,  ["stress test"]),
        (70,  ["interest", "rate decision", "federal funds rate", "target range"]),
        (60,  ["testimony", "speech", "governor"]),
        (50,  ["financial stability", "financial stability report", "stablecoin"]),
    ],
    "ECB": [
        (100, ["monetary policy decision", "interest rate decision", "monetary policy statement"]),
        (90,  ["account of the monetary policy"]),
        (80,  ["press conference", "ecb press conference"]),
        (70,  ["interest rate", "key ecb interest rate"]),
        (60,  ["speech", "president", "lagarde", "cipollone", "elderson", "lane", "fireside chat", "outlook for", "executive board"]),
        (50,  ["financial stability review", "economic bulletin", "financial integration", "digital euro", "wage tracker"]),
    ],
    "BOE": [
        (100, ["bank rate", "monetary policy committee decision", "mpc decision"]),
        (90,  ["minutes of the monetary policy committee", "mpc minutes"]),
        (85,  ["monetary policy report", "mpc report"]),
        (80,  ["financial stability report", "financial policy committee"]),
        (70,  ["interest rate", "rate decision"]),
        (60,  ["speech", "governor", "bailey", "deputy governor"]),
    ],
    "BOJ": [
        (100, ["monetary policy decision", "monetary policy meeting", "interest rate decision"]),
        (90,  ["summary of opinions", "statement on monetary policy"]),
        (80,  ["outlook for economic activity", "outlook report"]),
        (70,  ["interest rate", "policy rate"]),
        (60,  ["speech", "governor", "ujida", "board member"]),
        (50,  ["financial system report", "financial stability"]),
    ],
    "BOK": [
        (100, ["monetary policy decision", "base rate decision", "interest rate decision"]),
        (90,  ["minutes of the monetary policy", "monetary policy board minutes"]),
        (80,  ["monetary policy report"]),
        (70,  ["interest rate", "base rate"]),
        (60,  ["speech", "governor", "press conference"]),
    ],
}

def score_news_item(item):
    source = item.get("source", "")
    title_lower = item.get("title", "").lower()
    keywords = IMPORTANT_KEYWORDS.get(source, [])
    for score, patterns in keywords:
        for pat in patterns:
            if pat in title_lower:
                return score
    return 10


def fetch_rss(feed_id, url):
    items = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.encoding = "utf-8"
        root = ET.fromstring(resp.content)
        for item_elem in root.iter("item"):
            title = item_elem.findtext("title", "")
            link = item_elem.findtext("link", "")
            pub_date = item_elem.findtext("pubDate", "")
            desc = item_elem.findtext("description", "")

            if not title:
                title_elem = item_elem.find("{http://www.w3.org/2005/Atom}title")
                if title_elem is not None:
                    title = title_elem.text or ""

            items.append({
                "title": title,
                "link": link,
                "pubDate": parse_rss_date(pub_date),
                "description": desc[:200] if desc else "",
                "source": feed_id
            })
            if len(items) >= 20:
                break
    except Exception:
        pass
    return items


@app.route("/api/news")
def get_news():
    all_news = []
    for feed in RSS_FEEDS:
        all_news.extend(fetch_rss(feed["id"], feed["url"]))

    for item in all_news:
        item["score"] = score_news_item(item)

    # Filter items within last 90 days
    from datetime import timedelta
    now_dt = datetime.now()
    cutoff_30 = (now_dt - timedelta(days=30)).strftime("%Y-%m-%d")
    cutoff_90 = (now_dt - timedelta(days=90)).strftime("%Y-%m-%d")

    def pick_best(items, max_per_src=2, limit=12):
        items = [i for i in items if i.get("score", 0) >= 50]
        # Group by date, then sort dates desc
        by_date = {}
        for item in items:
            d = item.get("pubDate", "")
            by_date.setdefault(d, []).append(item)
        sorted_dates = sorted(by_date.keys(), reverse=True)
        result = []
        per_source = {}
        for date in sorted_dates:
            date_items = sorted(by_date[date], key=lambda x: -x.get("score", 0))
            for item in date_items:
                src = item.get("source", "")
                if per_source.get(src, 0) >= max_per_src:
                    continue
                per_source[src] = per_source.get(src, 0) + 1
                result.append(item)
                if len(result) >= limit:
                    return result
        return result

    # Try 30-day window first, fall back to 90-day if needed
    recent_30 = [n for n in all_news if (n.get("pubDate") or "") >= cutoff_30]
    result = pick_best(recent_30, 2, 12)

    if len(result) < 12:
        recent_90 = [n for n in all_news if cutoff_90 <= (n.get("pubDate") or "") < cutoff_30]
        # Merge 90-day items preserving per_source cap across both windows
        merged = recent_30 + recent_90
        result = pick_best(merged, 2, 12)

    return jsonify(result)


# ─── /api (catch-all) ─────────────────────────────────────────────────────

@app.route("/api")
def index():
    return jsonify({
        "name": "FOMC Dashboard API",
        "endpoints": [
            "/api/meetings",
            "/api/meetings/csv?year=2026",
            "/api/sep",
            "/api/current-rate",
            "/api/global-rates",
            "/api/news"
        ]
    })

@app.route("/")
def root():
    return app.send_static_file("index.html")

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
