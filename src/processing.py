
import json
from pathlib import Path
import pandas as pd

def load_hansard_items(raw_dir):
    """
    Load individual Hansard debate JSON files and combine
    their contributions into a single pandas DataFrame.

    Each row represents one Hansard item.
    """

    raw_dir = Path(raw_dir)
    files = sorted(raw_dir.glob("*.json"))

    if not files:
        raise FileNotFoundError(f"No JSON files found in {raw_dir}")

    frames = []

    for file in files:

        with open(file, encoding="utf-8") as f:
            debate = json.load(f)

        df = pd.json_normalize(debate["Items"])

        df["debate_id"] = debate["Overview"]["ExtId"]
        df["debate_title"] = debate["Overview"]["Title"].strip()
        df["debate_date"] = debate["Overview"]["Date"][:10]

        frames.append(df)

    items = pd.concat(frames, ignore_index=True)

    print(f"Loaded {len(files)} debate files.")
    print(f"Collected {len(items)} Hansard items.")

    return items