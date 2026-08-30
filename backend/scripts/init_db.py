"""
Create the schema and optionally load reference and demo data.

    python -m scripts.init_db                 # schema only
    python -m scripts.init_db --seed          # schema + reference/demo data
    python -m scripts.init_db --seed --test-data   # + a full demo scenario

Run from the ``backend/`` directory.
"""
import argparse
import sys

from dotenv import load_dotenv

load_dotenv()

from app.config import db  # noqa: E402
from app.config.settings import settings  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description="Initialise the KisanLink database.")
    parser.add_argument("--seed", action="store_true", help="load reference and demo data")
    parser.add_argument(
        "--test-data", action="store_true", help="load the end-to-end demo scenario"
    )
    args = parser.parse_args(argv)

    backend = db.active_backend()
    target = settings.SQLITE_PATH if backend == "sqlite" else (
        f"{settings.DB_USER}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
    )
    print(f"Using {backend} at {target}")

    connected, message = db.check_db_connection()
    if not connected:
        print(f"ERROR: {message}", file=sys.stderr)
        if backend == "mysql":
            print(
                "\nHint: create the database first:\n"
                "  mysql -u root -p -e \"CREATE DATABASE IF NOT EXISTS kisanlink_db\"",
                file=sys.stderr,
            )
        return 1

    db.init_schema()
    print("Schema created (existing tables were left untouched).")

    if args.seed:
        db.load_seed_data("seed.sql")
        print("Reference and demo data loaded.")
    if args.test_data:
        db.load_seed_data("test_data.sql")
        print("End-to-end demo scenario loaded.")

    print("\nDone. Start the API with: python run.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
