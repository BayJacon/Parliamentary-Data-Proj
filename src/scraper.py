
#===== IMPORTS =====#

import csv
import json
import re
import time
from collections import Counter
from datetime import date
from pathlib import Path

import requests


#===== CONFIGURATION =====#

# Which part of Parliament to collect
HOUSE = "Commons"                 # "Commons" or "Lords"

# Date range
START = date(2026, 10, 27)
END = date(2026, 10, 29)

# Contact details for API requests
CONTACT = "jaybacon234@gmail.com"

# Run size controls
MAX_DEBATES = 8                   # Set to None for the full dataset
TAKE = 10                         # Results per API page

# Request settings
DELAY = 1.0                       # Seconds between requests

# Output directories
OUT_DIR = Path("data")
RAW_DIR = OUT_DIR / "raw"
PROCESSED_DIR = OUT_DIR / "processed"

# Hansard API
API = "https://hansard-api.parliament.uk"

# Request headers
HEADERS = {
    "User-Agent": f"research-script ({CONTACT})"
}

# Titles to exclude
BLOCKLIST = {
    "ways and means",
    "personal statement",
    "business of the house",
    "arrangement of business",
    "petitions",
    "business without debate",
    "point of order"
}


#===== CREATE OUTPUT DIRECTORIES =====#

RAW_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


#===== SESSION =====#

session = requests.Session()
session.headers.update(HEADERS)


#===== HELPER FUNCTIONS =====#

def get_json(url, params=None, retries=3):
    """
    GET a URL and return parsed JSON, with polite delay and simple retries.
    """

    for attempt in range(1, retries + 1):
        try:
            r = session.get(url, params=params, timeout=30)

        except requests.RequestException as e:
            if attempt == retries:
                raise

            print(f"  network error ({e}); retry {attempt}/{retries - 1}")
            time.sleep(DELAY * attempt * 2)
            continue

        if r.status_code == 403:
            raise RuntimeError(
                f"403 Forbidden from {r.url}. "
                f"Server={r.headers.get('Server')}, "
                f"CF-Ray={r.headers.get('CF-Ray')}. "
                "Possibly bot protection."
            )

        if r.status_code in (429, 500, 502, 503, 504) and attempt < retries:
            print(f"  HTTP {r.status_code}; retry {attempt}/{retries - 1}")
            time.sleep(DELAY * attempt * 2)
            continue

        r.raise_for_status()
        time.sleep(DELAY)

        return r.json()


def strip_html(s):
    """
    Remove HTML tags from a string.
    """

    return re.sub(r"<[^>]+>", "", s or "").strip()


#===== FETCH DEBATE LIST =====#

def fetch_debate_list(house, start_date, end_date,
                      max_debates=MAX_DEBATES, take=TAKE):
    """
    Retrieve a list of Hansard debate sections for a House and date range.
    """

    results = []
    seen = set()
    skip = 0

    for _ in range(500):

        data = get_json(f"{API}/search/debates.json", {
            "queryParameters.house": house,
            "queryParameters.startDate": start_date.isoformat(),
            "queryParameters.endDate": end_date.isoformat(),
            "queryParameters.orderBy": "SittingDateAsc",
            "queryParameters.skip": skip,
            "queryParameters.take": take,
        })

        batch = data.get("Results", [])
        total = data.get("TotalResultCount", 0)

        if skip == 0:
            print("TotalResultCount:", total)

            if total > 50_000:
                raise RuntimeError(
                    "Total is huge, so the date/house filters may not "
                    "be working. Check the API parameter names."
                )

        if not batch:
            break

        for r in batch:
            debate_id = r["DebateSectionExtId"]

            if debate_id not in seen:
                seen.add(debate_id)
                results.append(r)

                if max_debates is not None and len(results) >= max_debates:
                    break

        skip += len(batch)

        limit_str = (
            f"limit: {max_debates}"
            if max_debates is not None
            else "no limit"
        )

        print(f"Fetched {len(results)} of {total} ({limit_str})")

        if skip >= total or (
            max_debates is not None and len(results) >= max_debates
        ):
            break

    return results