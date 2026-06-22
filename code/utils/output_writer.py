"""
Output writer: writes the final output.csv with exact column ordering and validation.
"""
import csv
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rules import OUTPUT_COLUMNS, validate_row


def write_output(rows: list[dict], path: str) -> None:
    """
    Write output rows to CSV with the exact 14-column order.
    Validates each row before writing — raises ValueError on invalid data.
    """
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=OUTPUT_COLUMNS,
            quoting=csv.QUOTE_ALL,
            extrasaction="ignore",
        )
        writer.writeheader()

        for i, row in enumerate(rows):
            # Validate before writing
            claim_object = row.get("claim_object", "car")
            try:
                validate_row(row, claim_object)
            except ValueError as e:
                print(f"  VALIDATION ERROR row {i} (user={row.get('user_id')}): {e}")
                raise

            writer.writerow(row)

    print(f"Output written: {path} ({len(rows)} rows)")
