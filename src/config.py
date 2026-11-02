from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
RAW_HANSARD = DATA_DIR / "raw" / "hansard"
RAW_MEMBERS = DATA_DIR / "raw" / "members"
PROCESSED = DATA_DIR / "processed"

for d in (RAW_HANSARD, RAW_MEMBERS, PROCESSED):
    d.mkdir(parents=True, exist_ok=True)