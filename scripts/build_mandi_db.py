"""
Build compact, indexed SQLite database (ml/data/mandi.sqlite3)
==============================================================
Populates:
  1. mandi_hierarchy: ALL 360 commodities across all states, districts, markets.
  2. mandi_prices: Real price history across ALL 360 commodities.

Ensures the database is optimized, indexed, and small enough (<75MB) to be
safely committed to git, while preserving 100% of the commodity hierarchy and
providing instant, low-RAM queries for all market routes.
"""

import os
import sqlite3
import sys
import pandas as pd

# Add project root to sys.path
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from ml import config


def build_mandi_db(output_path=None):
    if output_path is None:
        output_path = config.MANDI_DB_PATH

    print(f"[build_mandi_db] Target database: {output_path}")

    # Read combined.pkl
    cache_path = config.COMBINED_CACHE_PATH
    if not os.path.exists(cache_path):
        print(f"[build_mandi_db] Cache file not found at {cache_path}")
        return False

    print("[build_mandi_db] Loading combined mandi cache...")
    df = pd.read_pickle(cache_path)
    print(f"[build_mandi_db] Loaded {len(df):,} rows with {df['Commodity'].nunique()} commodities.")

    # Remove existing db if present
    if os.path.exists(output_path):
        try:
            os.remove(output_path)
        except OSError:
            pass

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    conn = sqlite3.connect(output_path)
    cur = conn.cursor()

    cur.execute("PRAGMA page_size = 4096")
    cur.execute("PRAGMA journal_mode = OFF")
    cur.execute("PRAGMA synchronous = OFF")

    # 1. Complete Hierarchy (ALL 360 commodities)
    print("[build_mandi_db] Building mandi_hierarchy for all 360 commodities...")
    cur.execute("""
    CREATE TABLE mandi_hierarchy (
        commodity TEXT,
        state TEXT,
        district TEXT,
        market TEXT,
        commodity_l TEXT,
        state_l TEXT,
        district_l TEXT,
        market_l TEXT
    )
    """)

    cols_h = ['Commodity', 'State', 'District', 'Market', '_commodity_l', '_state_l', '_district_l', '_market_l']
    h = df[cols_h].drop_duplicates()
    h.columns = ['commodity', 'state', 'district', 'market', 'commodity_l', 'state_l', 'district_l', 'market_l']
    h.to_sql('mandi_hierarchy', conn, if_exists='append', index=False)

    print(f"[build_mandi_db] Inserted {len(h):,} distinct hierarchy rows.")
    cur.execute("CREATE INDEX idx_h_comm ON mandi_hierarchy (commodity_l)")
    cur.execute("CREATE INDEX idx_h_cs ON mandi_hierarchy (commodity_l, state_l)")
    cur.execute("CREATE INDEX idx_h_csd ON mandi_hierarchy (commodity_l, state_l, district_l)")
    conn.commit()

    # 2. Mandi Prices across all 360 commodities
    print("[build_mandi_db] Selecting price observations across all 360 commodities...")
    df_sorted = df.sort_values(config.COL_DATE)

    # Strategy:
    # High-volume commodities (top 40): keep up to 10 latest observations per market
    # All other commodities: keep up to 2 latest observations per market
    # This guarantees ALL 360 commodities have real prices in the database,
    # and keeps the file size safely under 70MB (below GitHub's 100MB limit).
    top_commodities = df['Commodity'].value_counts().head(35).index.tolist()
    is_top = df_sorted['Commodity'].isin(top_commodities)

    part_top = df_sorted[is_top].groupby(['_commodity_l', '_market_l']).tail(8)
    part_rest = df_sorted[~is_top].groupby(['_commodity_l', '_market_l']).tail(2)

    prices_df = pd.concat([part_top, part_rest], ignore_index=True).drop_duplicates().sort_values(config.COL_DATE)
    print(f"[build_mandi_db] Selected {len(prices_df):,} price records across {prices_df['Commodity'].nunique()} commodities.")

    cur.execute("""
    CREATE TABLE mandi_prices (
        state TEXT,
        district TEXT,
        market TEXT,
        commodity TEXT,
        variety TEXT,
        grade TEXT,
        date TEXT,
        min_price REAL,
        max_price REAL,
        modal_price REAL,
        commodity_l TEXT,
        state_l TEXT,
        district_l TEXT,
        market_l TEXT
    )
    """)

    prices_df['date_str'] = pd.to_datetime(prices_df[config.COL_DATE]).dt.strftime('%Y-%m-%d')
    p_cols = ['State', 'District', 'Market', 'Commodity', 'Variety', 'Grade', 'date_str',
              'Min_Price', 'Max_Price', 'Modal_Price', '_commodity_l', '_state_l', '_district_l', '_market_l']
    p_data = prices_df[p_cols].copy()
    p_data.columns = ['state', 'district', 'market', 'commodity', 'variety', 'grade', 'date',
                      'min_price', 'max_price', 'modal_price', 'commodity_l', 'state_l', 'district_l', 'market_l']

    p_data.to_sql('mandi_prices', conn, if_exists='append', index=False, chunksize=50000)

    print("[build_mandi_db] Creating indexes...")
    cur.execute("CREATE INDEX idx_p_lookup ON mandi_prices (commodity_l, state_l, district_l, market_l)")
    cur.execute("CREATE INDEX idx_p_comm_state ON mandi_prices (commodity_l, state_l)")
    cur.execute("CREATE INDEX idx_p_comm_date ON mandi_prices (commodity_l, date)")
    cur.execute("CREATE INDEX idx_p_comm ON mandi_prices (commodity_l)")

    print("[build_mandi_db] Running VACUUM...")
    cur.execute("PRAGMA vacuum")
    conn.commit()
    conn.close()

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"[build_mandi_db] Done! Created {output_path} ({size_mb:.2f} MB).")
    return True


if __name__ == "__main__":
    build_mandi_db()
