"""
Drop every KisanLink table and rebuild from scratch.

    python -m scripts.reset_db --yes

Destructive. Refuses to run without the explicit flag.
"""
import argparse
import sys

from dotenv import load_dotenv

load_dotenv()

from app.config import db  # noqa: E402

#: Child tables first so foreign keys never block a drop.
DROP_ORDER = (
    "grievances",
    "ratings",
    "payments",
    "transaction_status_history",
    "logistics_requests",
    "transactions",
    "recommendations",
    "offers",
    "buyer_requirements",
    "lot_contributions",
    "lots",
    "price_forecasts",
    "market_data",
    "storage_facilities",
    "markets",
    "crops",
    "fpo_members",
    "fpo_profiles",
    "buyer_profiles",
    "farmer_profiles",
    "users",
)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Drop and rebuild the KisanLink schema.")
    parser.add_argument("--yes", action="store_true", help="confirm that data will be destroyed")
    parser.add_argument("--seed", action="store_true", help="reload seed data afterwards")
    args = parser.parse_args(argv)

    if not args.yes:
        print("Refusing to drop tables without --yes.", file=sys.stderr)
        return 1

    connection = db.get_db_connection()
    cursor = connection.cursor()
    if db.active_backend() == "mysql":
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
    for table in DROP_ORDER:
        cursor.execute(f"DROP TABLE IF EXISTS {table}")
        print(f"dropped {table}")
    if db.active_backend() == "mysql":
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
    connection.commit()
    cursor.close()

    db.init_schema()
    print("Schema rebuilt.")
    if args.seed:
        db.load_seed_data("seed.sql")
        print("Seed data reloaded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
