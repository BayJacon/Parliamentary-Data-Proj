"""Build a reference table of current MPs from the UK Parliament Members API.

Run from the project root:
    python -m src.mp_scraper               # fetch fresh data, rebuild and save the table
    python -m src.mp_scraper --use-saved   # rebuild the table from the saved raw JSON

From a notebook (project root on sys.path):
    from src.mp_scraper import update_mps
    mps = update_mps(refetch=False)        # reuse the saved raw file, no API calls
"""

import argparse
import json
import os
import time

import pandas as pd
import requests

from src.config import RAW_MEMBERS, PROCESSED


#===== SETTINGS =====#

MEMBERS_API = "https://members-api.parliament.uk/api"
TAKE = 20                          # the API's maximum page size
DELAY = 0.5                        # seconds between requests
HOUSE_COMMONS = 1

# Same environment variable as debate_scraper:  $env:HANSARD_CONTACT = "you@example.com"
CONTACT = os.environ.get("HANSARD_CONTACT", "your-email@example.com")
HEADERS = {"User-Agent": f"research-script ({CONTACT})"}

RAW_PATH = RAW_MEMBERS / "members_current_raw.json"

# column name in our table -> path inside each member's "value" object.
# To add a column, add a line. Everything else the API returns stays in the raw JSON.
FIELDS = {
    # identity
    "member_id":        "id",
    "name":             "nameDisplayAs",
    "name_list_as":     "nameListAs",
    "gender":           "gender",
    # party
    "party_id":         "latestParty.id",
    "party":            "latestParty.name",
    "party_abbr":       "latestParty.abbreviation",
    # constituency and membership
    "constituency_id":  "latestHouseMembership.membershipFromId",
    "constituency":     "latestHouseMembership.membershipFrom",
    "membership_start": "latestHouseMembership.membershipStartDate",
}
ID_COLUMNS = ["member_id", "party_id", "constituency_id"]

session = requests.Session()
session.headers.update(HEADERS)


#===== FETCH =====#

def _get_page(params, retries=3):
    """GET one page of search results, with simple retries."""
    for attempt in range(1, retries + 1):
        try:
            r = session.get(f"{MEMBERS_API}/Members/Search", params=params, timeout=30)
        except requests.RequestException as e:
            if attempt == retries:
                raise
            print(f"  network error ({e}); retry {attempt}/{retries - 1}")
            time.sleep(DELAY * attempt * 2)
            continue

        if r.status_code in (429, 500, 502, 503, 504) and attempt < retries:
            print(f"  HTTP {r.status_code}; retry {attempt}/{retries - 1}")
            time.sleep(DELAY * attempt * 2)
            continue

        r.raise_for_status()
        return r.json()


def fetch_current_mps():
    """Fetch every current member of the Commons from the API (about 33 requests)."""
    items, skip = [], 0
    for _ in range(300):                       # hard cap on pages
        data = _get_page({"House": HOUSE_COMMONS, "IsCurrentMember": "true",
                          "skip": skip, "take": TAKE})
        batch, total = data["items"], data["totalResults"]

        if skip == 0:
            print("totalResults:", total)
            if total > 1000:
                raise RuntimeError("Total is far above 650, so a filter was probably not applied.")
        if not batch:
            break

        items += batch
        skip += len(batch)
        if skip >= total:
            break
        time.sleep(DELAY)

    print(f"Fetched {len(items)} members")
    return items


#===== RAW FILE =====#

def save_raw(items, path=RAW_PATH):
    """Save the API response exactly as received (written via a temp file)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2)
    tmp.replace(path)
    print("Saved raw data to", path)


def load_raw(path=RAW_PATH):
    """Load the saved raw API response."""
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run with refetch=True (or without --use-saved).")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


#===== BUILD TABLE =====#

def build_mps_table(items):
    """Flatten the raw API items into one tidy row per MP, using the FIELDS map."""
    flat = pd.json_normalize([it["value"] for it in items])

    absent = [p for p in FIELDS.values() if p not in flat.columns]
    if absent:
        print("WARNING: not found in the data (check spelling, or empty for everyone):", absent)

    mps = flat.reindex(columns=list(FIELDS.values()))
    mps.columns = list(FIELDS.keys())

    for col in ID_COLUMNS:
        mps[col] = pd.to_numeric(mps[col], errors="coerce").astype("Int64")
    mps["membership_start"] = pd.to_datetime(
        mps["membership_start"].astype("string").str[:10], errors="coerce")

    return mps


#===== CHECKS =====#

def check_mps(mps):
    """Print the sanity checks to read by eye after each rebuild."""
    print(f"Rows: {len(mps)}")
    print(f"Unique member IDs:       {mps['member_id'].nunique()} (should equal rows)")
    print(f"Unique constituency IDs: {mps['constituency_id'].nunique()} (should equal rows)")
    print("\nParties:\n", mps["party"].value_counts(dropna=False).to_string())
    print("\nGender:\n", mps["gender"].value_counts(dropna=False).to_string())

    missing = mps.isna().sum()
    print("\nColumns with missing values:\n",
          missing[missing > 0].to_string() if missing.any() else "  none")


#===== SAVE =====#

def save_mps(mps):
    """Write the table to data/processed/mps_current.csv, replacing the previous version."""
    PROCESSED.mkdir(parents=True, exist_ok=True)
    path = PROCESSED / "mps_current.csv"
    mps.to_csv(path, index=False)
    print("Saved", path)
    return path


#===== PIPELINE =====#

def update_mps(refetch=True, save=True, check=True):
    """Fetch (or reload) the raw data, build the table, check it, save it. Returns the table."""
    if refetch or not RAW_PATH.exists():
        items = fetch_current_mps()
        save_raw(items)
    else:
        items = load_raw()
        print(f"Loaded {len(items)} members from {RAW_PATH}")

    mps = build_mps_table(items)
    if check:
        print()
        check_mps(mps)
    if save:
        print()
        save_mps(mps)
    return mps


def main():
    parser = argparse.ArgumentParser(description="Build the current-MPs reference table.")
    parser.add_argument("--use-saved", action="store_true",
                        help="rebuild from the saved raw JSON instead of calling the API")
    args = parser.parse_args()
    update_mps(refetch=not args.use_saved)


if __name__ == "__main__":
    main()