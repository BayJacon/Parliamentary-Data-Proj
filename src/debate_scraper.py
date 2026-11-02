"""Collect Hansard debates from the UK Parliament Hansard API.

Run from the project root:
    python -m src.debate_scraper 2026-10-27 2026-10-29
    python -m src.debate_scraper 2026-10-27 2026-10-29 --house Commons --max-debates 20

From a notebook:
    from src.debate_scraper import scrape_hansard
    summary, failures = scrape_hansard("2026-10-27", "2026-10-29", max_debates=None)
"""

import argparse
import csv
import json
import os
import re
import time
from collections import Counter
from datetime import date

import requests

from src.config import RAW_HANSARD, PROCESSED


#===== SETTINGS =====#

HOUSE = "Commons"                 # "Commons" or "Lords"
MAX_DEBATES = 8                   # Default cap for test runs. Pass max_debates=None for everything
TAKE = 10                         # Results per API page (try 100; the loop copes if the API caps it)
DELAY = 1.0                       # Seconds between requests

# Contact address sent in the User-Agent header. Read from an environment variable so
# your email address isn't committed to GitHub. In PowerShell:  $env:HANSARD_CONTACT = "you@example.com"
CONTACT = os.environ.get("HANSARD_CONTACT", "your-email@example.com")

API = "https://hansard-api.parliament.uk"
HEADERS = {"User-Agent": f"research-script ({CONTACT})"}

# Section titles to exclude (compared lowercase and stripped)
BLOCKLIST = {
    "ways and means",
    "personal statement",
    "business of the house",
    "arrangement of business",
    "petitions",
    "business without debate",
    "point of order",
    "points of order",
}

session = requests.Session()
session.headers.update(HEADERS)


#===== HELPERS =====#

def get_json(url, params=None, retries=3):
    """GET a URL and return parsed JSON, with a polite delay and simple retries."""
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
                f"403 Forbidden from {r.url}. Server={r.headers.get('Server')}, "
                f"CF-Ray={r.headers.get('CF-Ray')}. Possibly bot protection."
            )

        if r.status_code in (429, 500, 502, 503, 504) and attempt < retries:
            print(f"  HTTP {r.status_code}; retry {attempt}/{retries - 1}")
            time.sleep(DELAY * attempt * 2)
            continue

        r.raise_for_status()
        time.sleep(DELAY)
        return r.json()


def strip_html(s):
    """Remove HTML tags, leaving a single space where each tag was."""
    text = re.sub(r"<[^>]+>", " ", s or "")
    return " ".join(text.split())


#===== FETCH DEBATE LIST =====#

def fetch_debate_list(house, start_date, end_date, max_debates=MAX_DEBATES, take=TAKE):
    """Retrieve debate sections for a House and date range, paging through the API."""
    results, seen = [], set()
    skip, total, truncated = 0, 0, False

    for _ in range(500):                      # hard cap on pages, avoids infinite loops
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
                    "Total is huge, so the date/house filters may not be working. "
                    "Check the API parameter names."
                )
        if not batch:
            break

        for r in batch:
            if r["DebateSectionExtId"] not in seen:
                seen.add(r["DebateSectionExtId"])
                results.append(r)
                if max_debates is not None and len(results) >= max_debates:
                    truncated = True
                    break

        skip += len(batch)
        limit_str = f"limit: {max_debates}" if max_debates is not None else "no limit"
        print(f"Fetched {len(results)} of {total} ({limit_str})")

        if skip >= total or truncated:
            break

    if truncated:
        print(f"NOTE: stopped at max_debates={max_debates}, but {total} sections are available. "
              "Pass max_debates=None to fetch them all.")
    return results


#===== FILTER DEBATES =====#

def keep_debate(r, house, start_date, end_date, blocklist=BLOCKLIST):
    """True if a section is a main-chamber item in range and not on the blocklist."""
    return (
        r["House"] == house
        and r["DebateSection"] == f"{house} Chamber"
        and start_date.isoformat() <= r["SittingDate"][:10] <= end_date.isoformat()
        and r["Title"].strip().lower() not in blocklist
    )


def filter_debates(results, house, start_date, end_date, blocklist=BLOCKLIST):
    """Split sections into (wanted, excluded)."""
    wanted, excluded = [], []
    for r in results:
        (wanted if keep_debate(r, house, start_date, end_date, blocklist) else excluded).append(r)
    wanted.sort(key=lambda r: (r["SittingDate"], r["Title"].strip()))
    return wanted, excluded


#===== DOWNLOAD FULL DEBATES =====#

def load_or_download(debate_id, path):
    """Return a debate's JSON, reusing the saved file if it is intact.

    New downloads are written to a temporary file first and then renamed, so an
    interrupted run can never leave a half-written .json behind.
    """
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"  {path.name} is corrupt; downloading again")

    data = get_json(f"{API}/debates/debate/{debate_id}.json")
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    tmp.replace(path)
    return data


def download_debates(wanted):
    """Download each selected debate to data/raw/hansard/ and build summary records.

    Returns (summary, failures).
    """
    RAW_HANSARD.mkdir(parents=True, exist_ok=True)
    summary, failures = [], []

    for n, r in enumerate(wanted, 1):
        debate_id = r["DebateSectionExtId"]
        path = RAW_HANSARD / f'{r["SittingDate"][:10]}_{debate_id}.json'

        try:
            data = load_or_download(debate_id, path)
        except Exception as e:
            print(f"[{n}/{len(wanted)}] FAILED {debate_id} ({r['Title'].strip()}): {e}")
            failures.append(debate_id)
            continue

        items = data.get("Items", [])
        row = {
            "id": debate_id,
            "date": data["Overview"]["Date"][:10],
            "title": data["Overview"]["Title"].strip(),
            "n_items": len(items),
            "n_speakers": len({i["MemberId"] for i in items if i.get("MemberId")}),
            "n_children": len(data.get("ChildDebates", [])),
            "words": sum(len(strip_html(i.get("Value")).split()) for i in items),
            "file": path.name,
        }
        summary.append(row)

        print(
            f"[{n}/{len(wanted)}] {row['date']} | {row['title']} | "
            f"{row['n_items']} items, {row['n_speakers']} speakers, "
            f"{row['words']} words, {row['n_children']} children"
        )

    print(f"\nDone. {len(summary)} downloaded, {len(failures)} failed.")
    return summary, failures


#===== SAVE SUMMARY =====#

def save_summary(summary, start_date, end_date):
    """Save the debate summary as a date-labelled CSV in data/processed/."""
    if not summary:
        print("No summary records to save.")
        return None

    PROCESSED.mkdir(parents=True, exist_ok=True)
    csv_path = PROCESSED / f"debate_summary_{start_date}_{end_date}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=summary[0].keys())
        writer.writeheader()
        writer.writerows(summary)

    print(f"Saved summary to {csv_path}")
    return csv_path


#===== INTEGRITY CHECKS =====#

def check_integrity(summary, failures):
    """Flag failed downloads and debates that look empty or unusually short."""
    if failures:
        print("\nFAILED DOWNLOADS:")
        for debate_id in failures:
            print(f"  {debate_id}")

    for row in summary:
        if row["n_items"] == 0 and row["n_children"] > 0:
            print(f'Text may be in child sections: {row["title"]}')
        elif row["words"] < 300:
            print(f'Very short ({row["words"]} words): {row["title"]}')

    print("\nIntegrity checks complete.")


#===== MAIN PIPELINE =====#

def scrape_hansard(start_date, end_date, house=HOUSE, max_debates=MAX_DEBATES,
                   take=TAKE, blocklist=BLOCKLIST):
    """Run the whole pipeline: list, filter, download, summarise, check.

    Dates may be date objects or 'YYYY-MM-DD' strings. Returns (summary, failures).
    """
    if isinstance(start_date, str):
        start_date = date.fromisoformat(start_date)
    if isinstance(end_date, str):
        end_date = date.fromisoformat(end_date)
    if start_date > end_date:
        raise ValueError("start_date must be before or equal to end_date.")

    print(f"\nStarting Hansard scrape: {start_date} to {end_date} ({house})")

    # 1. Retrieve debate metadata
    results = fetch_debate_list(house, start_date, end_date, max_debates, take)
    print("Dates covered:", sorted({r["SittingDate"][:10] for r in results}))

    # 2. Filter, and show what was dropped so the blocklist can be tuned
    wanted, excluded = filter_debates(results, house, start_date, end_date, blocklist)
    print(f"\nDebates retained: {len(wanted)}")
    print(f"Debates excluded: {len(excluded)}")
    for (section, title), n in sorted(Counter(
            (r["DebateSection"], r["Title"].strip()) for r in excluded).items()):
        print(f"  excluded: [{section}] {title}" + (f"  (x{n})" if n > 1 else ""))

    # 3. Download raw JSON
    print()
    summary, failures = download_debates(wanted)

    # 4. Save summary and 5. check integrity
    save_summary(summary, start_date, end_date)
    check_integrity(summary, failures)

    print("\nHansard scrape complete.")
    return summary, failures


def main():
    parser = argparse.ArgumentParser(description="Download Hansard debates for a date range.")
    parser.add_argument("start", help="first date, YYYY-MM-DD")
    parser.add_argument("end", help="last date, YYYY-MM-DD")
    parser.add_argument("--house", default=HOUSE, choices=["Commons", "Lords"])
    parser.add_argument("--max-debates", type=int, default=None,
                        help="stop after this many sections (default: no limit)")
    parser.add_argument("--take", type=int, default=TAKE, help="results per API page")
    args = parser.parse_args()

    scrape_hansard(args.start, args.end, house=args.house,
                   max_debates=args.max_debates, take=args.take)


if __name__ == "__main__":
    main()