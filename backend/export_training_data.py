# export_training_data.py
from pathlib import Path
import csv

from database import SessionLocal
from models import EmailLog


def map_label(row: EmailLog) -> str:
    """
    Decide final label for training from a DB row.
    Priority:
      1) ml_label (manual/ML label if present)
      2) category (fallback)
    """
    if row.ml_label:
        return row.ml_label.lower()

    if row.category:
        return row.category.lower()

    return "general"


def main():
    db = SessionLocal()
    try:
        rows = db.query(EmailLog).all()
    finally:
        db.close()

    base_dir = Path(__file__).parent
    csv_path = base_dir / "emails.csv"

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["text", "label"])

        for r in rows:
            text = (r.body or "").strip()
            if not text:
                continue  # skip empty

            label = map_label(r)
            writer.writerow([text, label])

    print(f"Wrote {csv_path} with {len(rows)} DB rows (some may be skipped if empty body).")


if __name__ == "__main__":
    main()