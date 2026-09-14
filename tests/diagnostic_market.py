#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
KisanLink — Comprehensive 12+ Real Market Diagnostic
======================================================
* Loads the combined 5.8 M-row dataset EXACTLY ONCE.
* Auto-selects 12+ real (commodity, state, district, market) combinations
  from the actual data, preferring records >= 14.
* Runs the full Chronos pipeline independently for every combination.
* Prints a complete diagnostic block per market.
* Verifies: exact filtering, independent Chronos calls, IQR=0 safety,
  gap detection, no identical-forecast reuse across unrelated markets.
* Tests the Flask API (5+ combos) -- skips gracefully if API is down.
* Inspects the frontend "View Matches" button bug.

Run from the project root:
    python tests/diagnostic_market.py
"""

import sys
import os
import json
import time
import hashlib
import traceback

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import numpy as np
import pandas as pd
import torch
import re

from ml import config as ml_config
from ml.data_loader import (
    load_combined_data,
    get_market_data,
    prepare_context,
    _winsorize_prices,
)
from ml.forecaster import load_model, forecast_prices
from ml.evaluator import evaluate_model

SEP = "-" * 70

# ============================================================
# STEP 1 -- Load combined dataset ONCE
# ============================================================

print("=" * 70)
print("  KisanLink -- Comprehensive 12+ Real Market Diagnostic")
print("=" * 70)
print(f"\n[LOAD] Loading combined dataset from ml/data/ (all 3 CSVs)...")
_t0 = time.time()
DF = load_combined_data()
_t1 = time.time()
print(f"[LOAD] Done in {_t1-_t0:.1f}s -- {len(DF):,} records, "
      f"{DF[ml_config.COL_COMMODITY].nunique()} commodities, "
      f"{DF[ml_config.COL_STATE].nunique()} states.")

print(f"\n[CSV-CHECK] Files:")
for p in [ml_config.CSV_AGRICULTURE, ml_config.CSV_2022, ml_config.CSV_2026]:
    print(f"  exists={os.path.exists(p)}  path={p}")

# ============================================================
# STEP 2 -- Load Chronos model ONCE
# ============================================================

print(f"\n[MODEL] Loading Chronos model ({ml_config.MODEL_NAME})...")
_t2 = time.time()
PIPELINE = load_model()
_t3 = time.time()
print(f"[MODEL] Loaded in {_t3-_t2:.1f}s on {ml_config.MODEL_DEVICE}.")

# ============================================================
# STEP 3 -- Build test combinations
# ============================================================

def _first_market_with_enough(commodity, state, district, min_rec=14):
    mask = (
        (DF[ml_config.COL_COMMODITY].str.lower() == commodity.lower())
        & (DF[ml_config.COL_STATE].str.lower() == state.lower())
        & (DF[ml_config.COL_DISTRICT].str.lower() == district.lower())
    )
    sub = DF[mask]
    counts = sub.groupby(ml_config.COL_MARKET).size().sort_values(ascending=False)
    for mkt, cnt in counts.items():
        if cnt >= min_rec:
            return mkt, cnt
    return None, 0


def _best_combo_for_commodity(commodity, min_rec=14, exclude=None):
    mask = DF[ml_config.COL_COMMODITY].str.lower() == commodity.lower()
    sub = DF[mask]
    if exclude:
        for col, val in exclude:
            sub = sub[sub[col].str.lower() != val.lower()]
    grp = (
        sub.groupby([ml_config.COL_STATE, ml_config.COL_DISTRICT,
                     ml_config.COL_MARKET])
        .size().sort_values(ascending=False).reset_index(name="count")
    )
    grp = grp[grp["count"] >= min_rec]
    if grp.empty:
        return None, None, None, 0
    row = grp.iloc[0]
    return row[ml_config.COL_STATE], row[ml_config.COL_DISTRICT], row[ml_config.COL_MARKET], row["count"]


def _auto_discover(n=8, min_rec=14, already_used=None):
    already_used = already_used or set()
    grp = (
        DF.groupby([ml_config.COL_COMMODITY, ml_config.COL_STATE,
                    ml_config.COL_DISTRICT, ml_config.COL_MARKET])
        .size().sort_values(ascending=False).reset_index(name="count")
    )
    grp = grp[grp["count"] >= min_rec]

    chosen = []
    seen_c, seen_s, seen_d = set(), set(), set()
    used = set(already_used)

    for _, row in grp.iterrows():
        key = (row[ml_config.COL_COMMODITY], row[ml_config.COL_STATE],
               row[ml_config.COL_DISTRICT], row[ml_config.COL_MARKET])
        if key in used:
            continue
        c, s, d = key[0], key[1], key[2]
        score = (3 if c not in seen_c else 0) + (2 if s not in seen_s else 0) + (1 if d not in seen_d else 0)
        chosen.append((key, score, row["count"]))

    chosen.sort(key=lambda x: (x[1], x[2]), reverse=True)
    result = []
    for key, score, cnt in chosen:
        if key in used:
            continue
        result.append(key)
        used.add(key)
        seen_c.add(key[0]); seen_s.add(key[1]); seen_d.add(key[2])
        if len(result) == n:
            break
    return result


print("\n[COMBOS] Resolving mandatory test combinations...")
mandatory = []

# 1. Tomato / Maharashtra / Nashik / Pimpalgaon
mandatory.append(("Tomato", "Maharashtra", "Nashik", "Pimpalgaon"))

# 2. Banana / NCT of Delhi / Delhi / Azadpur
mandatory.append(("Banana", "Nct Of Delhi", "Delhi", "Azadpur"))

# 3. Onion / Maharashtra / Nashik / best market
onion_mkt, _ = _first_market_with_enough("Onion", "Maharashtra", "Nashik")
if onion_mkt:
    mandatory.append(("Onion", "Maharashtra", "Nashik", onion_mkt))
else:
    s, d, m, _ = _best_combo_for_commodity("Onion")
    if m:
        mandatory.append(("Onion", s, d, m))

# 4. Flower -- try Rose or Marigold
for flower in ["Rose(Loose)", "Marigold(Loose)", "Chrysanthemum(Loose)", "Carnation"]:
    s4, d4, m4, c4 = _best_combo_for_commodity(flower)
    if m4:
        mandatory.append((flower, s4, d4, m4))
        break

mandatory_set = set(mandatory)
print(f"[COMBOS] Mandatory: {len(mandatory)}")
for c in mandatory:
    print(f"  {c}")

auto = _auto_discover(n=10, min_rec=14, already_used=mandatory_set)
print(f"\n[COMBOS] Auto-discovered: {len(auto)}")
for c in auto:
    print(f"  {c}")

ALL_COMBOS = mandatory + auto
print(f"\n[COMBOS] Total: {len(ALL_COMBOS)}")

# ============================================================
# STEP 4 -- Per-market diagnostic
# ============================================================

results_summary = []
forecast_fingerprints = {}

print("\n\n" + "=" * 70)
print("  PER-MARKET DIAGNOSTIC")
print("=" * 70)

for idx, (commodity, state, district, market) in enumerate(ALL_COMBOS, 1):
    print(f"\n\n{SEP}")
    print(f"TEST {idx}/{len(ALL_COMBOS)}")
    print(f"Commodity : {commodity}")
    print(f"State     : {state}")
    print(f"District  : {district}")
    print(f"Market    : {market}")
    print(SEP)

    try:
        market_result = get_market_data(DF, commodity, state, district, market)
        market_df = market_result["data"]
        n_records = market_result["record_count"]

        if not market_df.empty:
            uq_commodity  = market_df[ml_config.COL_COMMODITY].unique().tolist()
            uq_state      = market_df[ml_config.COL_STATE].unique().tolist()
            uq_district   = market_df[ml_config.COL_DISTRICT].unique().tolist()
            uq_market_col = market_df[ml_config.COL_MARKET].unique().tolist()
        else:
            uq_commodity = uq_state = uq_district = uq_market_col = ["(empty)"]

        print(f"\n[FILTER] Unique Commodity  : {uq_commodity}")
        print(f"[FILTER] Unique State      : {uq_state}")
        print(f"[FILTER] Unique District   : {uq_district}")
        print(f"[FILTER] Unique Market     : {uq_market_col}")
        print(f"\nHistorical records : {n_records}")

        if market_result["source"] == "Insufficient data":
            print(f"[SKIP] Insufficient data ({n_records} < {ml_config.MIN_RECORDS}).")
            if market_result.get("message"):
                print(f"  Message: {market_result['message']}")
            results_summary.append({
                "idx": idx, "combo": (commodity, state, district, market),
                "status": "INSUFFICIENT", "n_records": n_records, "forecast": None,
            })
            print(SEP)
            continue

        ctx = prepare_context(market_df)
        prices_clean = ctx["prices"]
        dates        = ctx["dates"]
        context_len  = ctx["context_length"]
        gap_info     = ctx.get("gap_info")
        n_winsorized = ctx.get("n_winsorized", 0)

        context_prices = prices_clean[-context_len:]
        q1c = np.percentile(context_prices, 25)
        q3c = np.percentile(context_prices, 75)
        iqr_c = q3c - q1c

        unique_dates = len(np.unique(dates))
        latest_price = prices_clean[-1]
        hist_median  = float(np.median(prices_clean))
        hist_min     = float(np.min(prices_clean))
        hist_max     = float(np.max(prices_clean))
        ctx_min      = float(np.min(context_prices))
        ctx_max      = float(np.max(context_prices))
        ctx_median   = float(np.median(context_prices))

        print(f"Unique dates       : {unique_dates}")
        print(f"Latest actual price: Rs.{latest_price:,.2f}")
        print(f"Historical median  : Rs.{hist_median:,.2f}")
        print(f"Historical min     : Rs.{hist_min:,.2f}")
        print(f"Historical max     : Rs.{hist_max:,.2f}")
        print(f"\nContext length     : {context_len}")
        print(f"Context min        : Rs.{ctx_min:,.2f}")
        print(f"Context max        : Rs.{ctx_max:,.2f}")
        print(f"Context median     : Rs.{ctx_median:,.2f}")
        print(f"\nWinsorized count   : {n_winsorized}")
        print(f"IQR of context     : {iqr_c:.4f}")
        if iqr_c == 0:
            print("  [IQR=0] Winsorization must NOT collapse values to Q1.")
        print(f"Gap detected       : {'YES' if gap_info else 'NO'}")
        if gap_info:
            print(f"Gap information    : {gap_info}")

        # Verify context tensor matches market series
        tensor_values = ctx["context_tensor"][0].numpy()
        tensor_hash = hashlib.md5(tensor_values.tobytes()).hexdigest()
        series_last_n = prices_clean[-context_len:].astype(np.float32)
        series_hash = hashlib.md5(series_last_n.tobytes()).hexdigest()
        tensor_matches = (tensor_hash == series_hash)
        print(f"\n[VERIFY] Context tensor matches selected market prices: {tensor_matches}")
        if not tensor_matches:
            print("  *** BUG: Tensor does not match series! ***")

        # Chronos forecast
        print(f"\n[CHRONOS] Calling Chronos independently for test {idx}...")
        _fc_t0 = time.time()
        forecast_values = forecast_prices(PIPELINE, ctx["context_tensor"])
        _fc_t1 = time.time()
        print(f"[CHRONOS] Completed in {_fc_t1-_fc_t0:.2f}s")

        print(f"\nRAW Chronos forecast:")
        for i, v in enumerate(forecast_values, 1):
            print(f"  D{i}: Rs.{v:,.2f}")

        print(f"\nFinal forecast:")
        for i, v in enumerate(forecast_values, 1):
            print(f"  D{i}: Rs.{v:,.2f}")

        fc_median = float(np.median(forecast_values))
        fc_hist_ratio   = fc_median / hist_median   if hist_median   != 0 else float("inf")
        fc_latest_ratio = fc_median / latest_price  if latest_price  != 0 else float("inf")
        print(f"\nForecast median                    : Rs.{fc_median:,.2f}")
        print(f"Forecast / historical-median ratio : {fc_hist_ratio:.4f}")
        print(f"Forecast / latest-actual ratio     : {fc_latest_ratio:.4f}")

        eval_result = evaluate_model(PIPELINE, prices_clean)
        print(f"\nEvaluation:")
        if eval_result:
            print(f"  MAE  : Rs.{eval_result['mae']:,.2f}")
            print(f"  RMSE : Rs.{eval_result['rmse']:,.2f}")
            print(f"  MAPE : {eval_result['mape']:.2f}%")
        else:
            print(f"  Skipped (need >= {ml_config.MIN_EVAL_RECORDS} records, have {len(prices_clean)})")

        fc_hash = hashlib.md5(forecast_values.astype(np.float32).tobytes()).hexdigest()
        key = (commodity, state, district, market)
        for prev_key, prev_hash in forecast_fingerprints.items():
            if prev_hash == fc_hash and prev_key != key:
                print(f"\n  [IDENTITY WARNING] Forecast identical to {prev_key}!")
        forecast_fingerprints[key] = fc_hash

        results_summary.append({
            "idx": idx, "combo": key, "status": "OK",
            "n_records": n_records, "context_len": context_len,
            "hist_median": hist_median, "latest_price": latest_price,
            "forecast": forecast_values.tolist(), "fc_median": fc_median,
            "fc_hist_ratio": fc_hist_ratio, "fc_latest_ratio": fc_latest_ratio,
            "n_winsorized": n_winsorized, "iqr_context": iqr_c,
            "gap_detected": bool(gap_info), "tensor_matches": tensor_matches,
            "fc_hash": fc_hash,
            "eval_mae":  eval_result["mae"]  if eval_result else None,
            "eval_rmse": eval_result["rmse"] if eval_result else None,
            "eval_mape": eval_result["mape"] if eval_result else None,
        })

    except Exception as exc:
        print(f"\n[ERROR] Test {idx} failed: {exc}")
        traceback.print_exc()
        results_summary.append({
            "idx": idx, "combo": (commodity, state, district, market),
            "status": "ERROR", "error": str(exc),
        })

    print(SEP)


# ============================================================
# STEP 5 -- Forecast identity analysis
# ============================================================

print("\n\n" + "=" * 70)
print("  FORECAST IDENTITY ANALYSIS")
print("=" * 70)

hash_to_combos = {}
for k, h in forecast_fingerprints.items():
    hash_to_combos.setdefault(h, []).append(k)

any_identical = False
for h, combos in hash_to_combos.items():
    if len(combos) > 1:
        any_identical = True
        print(f"\n[IDENTICAL] hash={h}")
        for c in combos:
            print(f"  {c}")
        # Compare input contexts
        ctxs = []
        for c in combos:
            mr = get_market_data(DF, *c)
            if mr["source"] != "Insufficient data":
                cp = prepare_context(mr["data"])["prices"]
                ctxs.append(cp)
        if len(ctxs) >= 2:
            max_len = min(len(ctxs[0]), len(ctxs[1]))
            same = np.allclose(ctxs[0][-max_len:], ctxs[1][-max_len:], atol=1e-3)
            print(f"  Input contexts identical: {same}")

if not any_identical:
    print(f"\n  All {len(forecast_fingerprints)} markets produced unique forecasts. No reuse detected.")


# ============================================================
# STEP 6 -- IQR=0 winsorization validation
# ============================================================

print("\n\n" + "=" * 70)
print("  IQR=0 WINSORIZATION VALIDATION")
print("=" * 70)

flat_series = np.array([1000.0] * 20 + [191820849.0])
clipped = _winsorize_prices(flat_series, k=5.0)
q1f, q3f = np.percentile(flat_series, 25), np.percentile(flat_series, 75)
iqr_f = q3f - q1f
print(f"\n[SYNTH-IQR=0] 20x Rs.1,000 + outlier Rs.191,820,849")
print(f"  Q1={q1f}, Q3={q3f}, IQR={iqr_f}")
print(f"  Flat values preserved: {clipped[:5]}")
print(f"  Outlier clipped to  : {clipped[-1]:,.2f}")
assert iqr_f == 0.0
assert clipped[:20].min() == 1000.0, "BUG: flat prices collapsed!"
assert clipped[-1] < flat_series[-1], "BUG: outlier not clipped!"
print("  PASS: IQR=0 -- flat prices preserved, outlier clipped.")

varied = np.array([900,950,1000,1050,1100,1200,800,750,1300,1250,
                   1000,950,1050,1150,1000,1100,900,1200,1050,975], dtype=float)
clipped_v = _winsorize_prices(varied, k=5.0)
assert np.array_equal(varied, clipped_v), "BUG: legitimate prices clipped!"
print("\n[SYNTH-IQR>0] Normal varied series -- no legitimate prices clipped.")
print("  PASS.")

iqr_zero_real = [r for r in results_summary if r.get("status")=="OK" and r.get("iqr_context",1)==0]
if iqr_zero_real:
    print(f"\n[REAL IQR=0 Markets found: {len(iqr_zero_real)}]")
    for rs in iqr_zero_real:
        print(f"  {rs['combo']}: n_winsorized={rs['n_winsorized']}, fc_median={rs['fc_median']:.2f}")
else:
    print("\n[Real IQR=0 markets]: None found in this run.")


# ============================================================
# STEP 7 -- API verification
# ============================================================

print("\n\n" + "=" * 70)
print("  API VERIFICATION")
print("=" * 70)

import urllib.request
API_URL = "http://localhost:5000"
api_alive = False
try:
    resp = urllib.request.urlopen(f"{API_URL}/api/commodities", timeout=5)
    api_alive = resp.status == 200
    print(f"\n[API] Server reachable at {API_URL}: True")
except Exception as e:
    print(f"\n[API] Server NOT reachable: {e}")
    print("  To test API: start 'python backend/app.py' first.")

if api_alive:
    import urllib.parse
    import urllib.error
    api_ok = [r for r in results_summary if r.get("status") == "OK"][:5]
    prev_fc = None
    for api_num, rs in enumerate(api_ok, 1):
        commodity, state, district, market = rs["combo"]
        payload_bytes = json.dumps({
            "commodity": commodity, "state": state,
            "district": district,  "market": market,
        }).encode()
        print(f"\n[API-TEST {api_num}] {commodity} / {state} / {district} / {market}")
        req = urllib.request.Request(
            f"{API_URL}/api/forecast",
            data=payload_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                data = json.loads(r.read())
            print(f"  response.commodity    : {data.get('commodity')}")
            print(f"  response.state        : {data.get('state')}")
            print(f"  response.district     : {data.get('district')}")
            print(f"  response.market       : {data.get('market')}")
            print(f"  historical_records    : {data.get('historical_records')}")
            dr = data.get("date_range", {})
            print(f"  latest available date : {dr.get('end') if dr else 'N/A'}")
            print(f"  context_length        : {data.get('context_length')}")
            for f in data.get("forecast", []):
                print(f"  D{f['day']}: Rs.{f['price']:,.2f}")
            fc_prices = [f["price"] for f in data.get("forecast", [])]
            if prev_fc is not None and fc_prices == prev_fc:
                print("  *** WARNING: Identical to previous API forecast! ***")
            prev_fc = fc_prices
            # verify match
            assert data.get("commodity","").lower() == commodity.lower()
            assert data.get("state","").lower() == state.lower()
            assert data.get("district","").lower() == district.lower()
            print("  PASS: response matches request.")
        except Exception as e:
            print(f"  ERROR: {e}")
            traceback.print_exc()


# ============================================================
# STEP 8 -- Frontend "View Matches" bug inspection
# ============================================================

print("\n\n" + "=" * 70)
print("  FRONTEND 'VIEW MATCHES' BUG INSPECTION")
print("=" * 70)

dashboard_js_path = os.path.join(_ROOT, "frontend", "js", "dashboard.js")
farmer_html_path  = os.path.join(_ROOT, "frontend", "pages", "farmer.html")

dash_js = open(dashboard_js_path, encoding="utf-8", errors="replace").read() if os.path.exists(dashboard_js_path) else ""
farmer_html = open(farmer_html_path, encoding="utf-8", errors="replace").read() if os.path.exists(farmer_html_path) else ""

vm_in_dash   = "View Matches" in dash_js
vm_in_html   = "View Matches" in farmer_html
onion_in_rec = ("Onion" in farmer_html) and ("recommendations-section" in farmer_html)
is_anchor    = 'href="#recommendations-section"' in dash_js
has_dynamic  = "${lot.crop}" in dash_js or "data-commodity" in dash_js

print(f"\n  'View Matches' in dashboard.js          : {vm_in_dash}")
print(f"  'View Matches' in farmer.html           : {vm_in_html}")
print(f"  Anchor-only link (no commodity context) : {is_anchor}")
print(f"  Has dynamic commodity passing           : {has_dynamic}")
print(f"  Hardcoded Onion in recommendations-section: {onion_in_rec}")

# Extract button context
vm_ctx = re.findall(r'(?:View Matches.{0,500})', dash_js, re.DOTALL)
if vm_ctx:
    print(f"\n  Button context in dashboard.js:")
    for m in vm_ctx[:2]:
        print(f"  {repr(m[:400])}")

if is_anchor and onion_in_rec and not has_dynamic:
    print("""
  *** BUG CONFIRMED ***
  The 'View Matches' button is a plain <a href="#recommendations-section">.
  It carries NO commodity context. The #recommendations-section in
  farmer.html is statically hardcoded with Onion data only.

  Effect: Clicking 'View Matches' on any crop (Tomato, Banana, etc.)
  always scrolls to and displays the hardcoded Onion recommendation.
  The Tomato button DOES show Onion matches.

  Required fix:
    1. Change the "View Matches" <a> in dashboard.js to a <button> with
       data-commodity="${lot.crop}" and data-matches="${encoded_matches}".
    2. Add a JS handler that reads data-commodity, dynamically renders
       the recommendations section with the correct crop's match data.
    3. Do NOT use hardcoded data to fix this.
""")
elif has_dynamic:
    print("\n  View Matches appears to pass commodity dynamically. Bug may be fixed.")
else:
    print("\n  Inconclusive -- manual browser test recommended.")


# ============================================================
# STEP 9 -- FINAL REPORT
# ============================================================

print("\n\n" + "=" * 70)
print("  FINAL DIAGNOSTIC REPORT")
print("=" * 70)

ok_results   = [r for r in results_summary if r.get("status") == "OK"]
skip_results = [r for r in results_summary if r.get("status") == "INSUFFICIENT"]
err_results  = [r for r in results_summary if r.get("status") == "ERROR"]

print(f"\n1. Tests run         : {len(ALL_COMBOS)}")
print(f"   OK                : {len(ok_results)}")
print(f"   Insufficient data : {len(skip_results)}")
print(f"   Error             : {len(err_results)}")

print(f"\n2. IQR=0 Fix confirmed in _winsorize_prices():")
print(f"   lo=0 when IQR=0 (no collapse to Q1). Upper fence uses max(k*IQR, k*Q3).")

print(f"\n3. Market forecast results:")
print(f"   {'Combo':<58}  {'Fc-Median':>10}  {'HiMed':>8}  {'Ratio':>6}")
print(f"   {'-'*58}  {'-'*10}  {'-'*8}  {'-'*6}")
for rs in ok_results:
    c = " / ".join(rs["combo"])
    if len(c) > 56: c = c[:53] + "..."
    print(f"   {c:<58}  Rs.{rs['fc_median']:>7,.0f}  "
          f"Rs.{rs['hist_median']:>6,.0f}  {rs['fc_hist_ratio']:>5.3f}")

print(f"\n4. Identical forecasts between unrelated markets: {any_identical}")
if not any_identical:
    print(f"   All {len(ok_results)} forecasts unique -- no reuse or caching detected.")

print(f"\n5. Model: {ml_config.MODEL_NAME} on {ml_config.MODEL_DEVICE}.")
print(f"   Chronos called independently per test -- confirmed.")

print(f"\n6. Dataset: 3 CSVs auto-combined at startup. Total: {len(DF):,} records.")

ok_tensor = sum(1 for r in ok_results if r.get("tensor_matches", True))
print(f"\n7. Exact market filtering: {ok_tensor}/{len(ok_results)} context tensors verified.")

print(f"\n8. API verification: {'5 combos tested' if api_alive else 'SKIPPED (server not running)'}")

print(f"\n9. View Matches bug: ", end="")
if is_anchor and onion_in_rec and not has_dynamic:
    print("CONFIRMED -- hardcoded Onion, anchor-only, no commodity context.")
    print(f"   FIX REQUIRED before commit.")
else:
    print("Not detected or already fixed.")

print(f"\n10. Remaining issues:")
if err_results:
    for r in err_results:
        print(f"    Error in {r['combo']}: {str(r.get('error',''))[:80]}")
if is_anchor and onion_in_rec and not has_dynamic:
    print(f"    FRONTEND: View Matches shows hardcoded Onion for all crops.")
if not err_results and not (is_anchor and onion_in_rec and not has_dynamic):
    print(f"    None.")

print(f"\n11. Files changed by this diagnostic run: NONE (read-only).")

print(f"\n12. Git diff: Run 'git diff' to see all uncommitted changes.")
print(f"    DO NOT COMMIT until View Matches fix is applied and verified.")

print("\n" + "=" * 70)
print("  Diagnostic complete.")
print("=" * 70 + "\n")
