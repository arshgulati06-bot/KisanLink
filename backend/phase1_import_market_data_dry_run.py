"""
KisanLink Phase 1 — Market Data Dry Run

Reads the cleaned Phase 1 CSV and verifies that:
- all 5 crops exist in the KisanLink crops table
- all CSV markets can be mapped to the existing markets table
- prices/date values are importable
- no duplicate full keys exist

IMPORTANT:
This version does NOT insert or modify any database rows.
"""

import csv
import os
from collections import Counter
from datetime import datetime

from dotenv import load_dotenv
import mysql.connector

load_dotenv()

CSV_FILE = os.path.join(os.path.dirname(__file__), "KisanLink_Phase1_MarketData.csv")

BATCH_REPORT_EVERY = 100_000


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
    return value.strip()


def main():
    print("=" * 60)
    print("KISANLINK PHASE 1 — MARKET DATA DRY RUN")
    print("=" * 60)
    print(f"CSV: {CSV_FILE}")
    print("DATABASE CHANGES: NONE")
    print()

    if not os.path.exists(CSV_FILE):
        print("ERROR: CSV file was not found.")
        print(f"Expected: {CSV_FILE}")
        return

    conn = get_connection()
    cursor = conn.cursor()

    # Load crop IDs.
    cursor.execute("SELECT id, name FROM crops")
    crop_map = {clean(name).lower(): crop_id for crop_id, name in cursor.fetchall()}

    # Load market IDs using the same identifying fields used by the imported master data.
    cursor.execute("SELECT id, name, district, state FROM markets")
    market_map = {
        (
            clean(name).lower(),
            clean(district).lower(),
            clean(state).lower(),
        ): market_id
        for market_id, name, district, state in cursor.fetchall()
    }

    print(f"Crops in DB: {len(crop_map)}")
    print(f"Markets in DB: {len(market_map)}")
    print()

    row_count = 0
    missing_crops = Counter()
    missing_markets = Counter()
    duplicate_keys = 0
    seen_keys = set()
    invalid_dates = 0
    invalid_prices = 0
    blank_prices = Counter()
    crop_counts = Counter()
    grade_counts = Counter()

    with open(CSV_FILE, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        expected = {
            "state", "district", "market", "commodity", "variety",
            "grade", "min_price", "max_price", "modal_price", "price_date"
        }

        actual = {clean(x).lower() for x in reader.fieldnames or []}
        if actual != expected:
            print("ERROR: CSV columns do not match expected cleaned format.")
            print("Found:", reader.fieldnames)
            print("Expected:", sorted(expected))
            return

        for row in reader:
            row_count += 1

            state = clean(row["state"])
            district = clean(row["district"])
            market = clean(row["market"])
            commodity = clean(row["commodity"])
            variety = clean(row["variety"]) or "General"
            grade = clean(row["grade"]) or "General"

            crop_key = commodity.lower()
            crop_counts[commodity] += 1
            grade_counts[grade] += 1

            if crop_key not in crop_map:
                missing_crops[commodity] += 1

            market_key = (market.lower(), district.lower(), state.lower())
            if market_key not in market_map:
                missing_markets[market_key] += 1

            date_value = clean(row["price_date"])
            try:
                datetime.strptime(date_value, "%Y-%m-%d")
            except ValueError:
                invalid_dates += 1

            for price_name in ("min_price", "max_price", "modal_price"):
                value = clean(row[price_name])
                if value == "":
                    blank_prices[price_name] += 1
                else:
                    try:
                        float(value)
                    except ValueError:
                        invalid_prices += 1

            full_key = (
                market_key,
                crop_key,
                variety.lower(),
                grade.lower(),
                date_value,
            )

            if full_key in seen_keys:
                duplicate_keys += 1
            else:
                seen_keys.add(full_key)

            if row_count % BATCH_REPORT_EVERY == 0:
                print(f"Rows checked: {row_count:,}")

    cursor.close()
    conn.close()

    print()
    print("=" * 60)
    print("DRY RUN RESULTS")
    print("=" * 60)
    print(f"Rows checked:        {row_count:,}")
    print(f"Unique full keys:    {len(seen_keys):,}")
    print(f"Duplicate full keys: {duplicate_keys:,}")
    print(f"Invalid dates:       {invalid_dates:,}")
    print(f"Invalid prices:      {invalid_prices:,}")
    print(f"Missing crop rows:   {sum(missing_crops.values()):,}")
    print(f"Missing market rows: {sum(missing_markets.values()):,}")
    print()

    print("Crop counts:")
    for crop, count in sorted(crop_counts.items()):
        print(f"  {crop}: {count:,}")

    print()
    print("Grade counts:")
    for grade, count in sorted(grade_counts.items()):
        print(f"  {grade}: {count:,}")

    print()
    print("Blank prices:")
    for name in ("min_price", "max_price", "modal_price"):
        print(f"  {name}: {blank_prices[name]:,}")

    if missing_crops:
        print()
        print("FIRST MISSING CROPS:")
        for crop, count in missing_crops.most_common(10):
            print(f"  {crop}: {count:,}")

    if missing_markets:
        print()
        print("FIRST MISSING MARKETS:")
        for key, count in missing_markets.most_common(10):
            print(f"  {key}: {count:,}")

    print()
    if (
        row_count == 737_392
        and duplicate_keys == 0
        and invalid_dates == 0
        and invalid_prices == 0
        and not missing_crops
        and not missing_markets
    ):
        print("DRY RUN PASSED — safe to proceed to the real batch import.")
    else:
        print("DRY RUN FOUND ISSUES — DO NOT IMPORT YET.")


if __name__ == "__main__":
    main()
