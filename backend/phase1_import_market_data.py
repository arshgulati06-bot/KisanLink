"""
KisanLink Phase 1 — Real Market Data Batch Import

Imports KisanLink_Phase1_MarketData.csv into market_data.

Requirements:
- Run from the backend folder with the project's .venv activated.
- CSV must be in the same backend folder as this script.
- Database master data (crops and markets) must already exist.

Import behavior:
- Batch size: 5,000 rows
- Blank prices -> SQL NULL
- price_unit -> QUINTAL
- source -> AGMARKNET
- arrival_quantity -> NULL (not present in CSV)
- arrival_unit -> TONNE
- Preserves variety and grade
- Uses the database unique key:
  market_id + crop_id + variety + grade + price_date
- Existing matching rows are updated rather than duplicated.
"""

import csv
import os
import sys
import time
from datetime import datetime

import mysql.connector
from dotenv import load_dotenv

load_dotenv()

CSV_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "KisanLink_Phase1_MarketData.csv",
)

BATCH_SIZE = 5000
PROGRESS_EVERY = 50_000


def get_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", "root"),
        database=os.getenv("DB_NAME", "kisanlink_db"),
    )


def clean(value):
    if value is None:
        return ""
    return str(value).strip()


def price_or_none(value):
    value = clean(value)
    return None if value == "" else float(value)


def main():
    print("=" * 65)
    print("KISANLINK PHASE 1 — REAL MARKET DATA IMPORT")
    print("=" * 65)
    print(f"CSV: {CSV_FILE}")
    print(f"Batch size: {BATCH_SIZE:,}")
    print("Database changes: YES")
    print()

    if not os.path.exists(CSV_FILE):
        print("ERROR: CSV file was not found.")
        print(f"Expected: {CSV_FILE}")
        sys.exit(1)

    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Load crop IDs.
        cursor.execute("SELECT id, name FROM crops")
        crop_map = {
            clean(name).lower(): crop_id
            for crop_id, name in cursor.fetchall()
        }

        # Load market IDs.
        cursor.execute("SELECT id, name, district, state FROM markets")
        market_map = {
            (
                clean(name).lower(),
                clean(district).lower(),
                clean(state).lower(),
            ): market_id
            for market_id, name, district, state in cursor.fetchall()
        }

        print(f"Crops loaded from DB:   {len(crop_map)}")
        print(f"Markets loaded from DB: {len(market_map)}")
        print()

        insert_sql = """
            INSERT INTO market_data (
                market_id,
                crop_id,
                variety,
                grade,
                price_date,
                min_price,
                max_price,
                modal_price,
                arrival_quantity,
                arrival_unit,
                price_unit,
                source
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s
            )
            ON DUPLICATE KEY UPDATE
                min_price = VALUES(min_price),
                max_price = VALUES(max_price),
                modal_price = VALUES(modal_price),
                arrival_quantity = VALUES(arrival_quantity),
                arrival_unit = VALUES(arrival_unit),
                price_unit = VALUES(price_unit),
                source = VALUES(source)
        """

        batch = []
        rows_processed = 0
        rows_committed = 0
        started = time.time()

        with open(CSV_FILE, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)

            expected = {
                "state", "district", "market", "commodity", "variety",
                "grade", "min_price", "max_price", "modal_price", "price_date"
            }

            actual = {clean(x).lower() for x in reader.fieldnames or []}
            if actual != expected:
                raise ValueError(
                    "CSV columns do not match the expected cleaned format.\n"
                    f"Found: {reader.fieldnames}\n"
                    f"Expected: {sorted(expected)}"
                )

            for row in reader:
                rows_processed += 1

                state = clean(row["state"])
                district = clean(row["district"])
                market = clean(row["market"])
                commodity = clean(row["commodity"])
                variety = clean(row["variety"]) or "General"
                grade = clean(row["grade"]) or "General"
                price_date = clean(row["price_date"])

                crop_id = crop_map.get(commodity.lower())
                if crop_id is None:
                    raise ValueError(
                        f"Crop mapping failed at CSV row {rows_processed}: "
                        f"{commodity!r}"
                    )

                market_key = (
                    market.lower(),
                    district.lower(),
                    state.lower(),
                )
                market_id = market_map.get(market_key)
                if market_id is None:
                    raise ValueError(
                        f"Market mapping failed at CSV row {rows_processed}: "
                        f"{market!r}, {district!r}, {state!r}"
                    )

                # Validate date while importing.
                datetime.strptime(price_date, "%Y-%m-%d")

                batch.append(
                    (
                        market_id,
                        crop_id,
                        variety,
                        grade,
                        price_date,
                        price_or_none(row["min_price"]),
                        price_or_none(row["max_price"]),
                        price_or_none(row["modal_price"]),
                        None,          # arrival_quantity not supplied
                        "TONNE",
                        "QUINTAL",
                        "AGMARKNET",
                    )
                )

                if len(batch) >= BATCH_SIZE:
                    cursor.executemany(insert_sql, batch)
                    conn.commit()
                    rows_committed += len(batch)
                    batch.clear()

                    if rows_committed % PROGRESS_EVERY == 0:
                        elapsed = time.time() - started
                        rate = rows_committed / elapsed if elapsed else 0
                        print(
                            f"Imported: {rows_committed:,} / 737,392 "
                            f"({rate:,.0f} rows/sec)"
                        )

            if batch:
                cursor.executemany(insert_sql, batch)
                conn.commit()
                rows_committed += len(batch)
                batch.clear()

        elapsed = time.time() - started

        print()
        print("=" * 65)
        print("IMPORT COMPLETE")
        print("=" * 65)
        print(f"Rows processed:  {rows_processed:,}")
        print(f"Rows committed:  {rows_committed:,}")
        print(f"Time taken:      {elapsed / 60:.2f} minutes")
        print(f"Average speed:   {rows_committed / elapsed:,.0f} rows/sec")
        print()
        print("Next step: verify market_data row count in MySQL.")

    except Exception:
        conn.rollback()
        print()
        print("IMPORT FAILED.")
        print("The current uncommitted batch was rolled back.")
        raise

    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
