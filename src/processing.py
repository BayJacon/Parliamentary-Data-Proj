"""Load saved Hansard debate JSON files into pandas.

From a notebook (project root on sys.path):
    from src.processing import load_hansard_items
    items = load_hansard_items()
"""

import json
from pathlib import Path

import pandas as pd

from src.config import RAW_HANSARD


def load_hansard_items(raw_dir=RAW_HANSARD):
    """Combine every saved debate file into one DataFrame, one row per Hansard item.

    Nothing is filtered here: speeches, headings and other item types are all kept
    (filter on the ItemType column afterwards). Extra columns identify the debate
    and the file each row came from.
    """
    raw_dir = Path(raw_dir)
    files = sorted(raw_dir.glob("*.json"))
    if not files:
        raise FileNotFoundError(f"No JSON files found in {raw_dir}")

    frames, unreadable, empty = [], [], []

    for file in files:
        try:
            with open(file, encoding="utf-8") as f:
                debate = json.load(f)
        except json.JSONDecodeError:
            unreadable.append(file.name)
            continue

        contributions = debate.get("Items", [])
        if not contributions:                  # no items (text may be in child sections)
            empty.append(file.name)
            continue

        overview = debate["Overview"]
        df = pd.json_normalize(contributions)
        df["debate_id"] = overview["ExtId"]
        df["debate_title"] = overview["Title"].strip()
        df["debate_date"] = overview["Date"][:10]
        df["source_file"] = file.name
        frames.append(df)

    if not frames:
        raise ValueError(f"None of the {len(files)} files in {raw_dir} contained any items.")

    items = pd.concat(frames, ignore_index=True)

    # Tidy types so later merges line up (MemberId is missing for non-speech items,
    # which would otherwise turn the whole column into floats like 4514.0)
    if "MemberId" in items.columns:
        items["MemberId"] = pd.to_numeric(items["MemberId"], errors="coerce").astype("Int64")
    items["debate_date"] = pd.to_datetime(items["debate_date"])

    print(f"Loaded {len(files) - len(unreadable) - len(empty)} debate files "
          f"-> {len(items)} Hansard items.")
    if empty:
        print(f"  {len(empty)} files had no items: {empty}")
    if unreadable:
        print(f"  WARNING: {len(unreadable)} unreadable files skipped: {unreadable}")

    return items