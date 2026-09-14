"""Fail if frontend market-intelligence still embeds fabricated mandi numbers."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FORBIDDEN_SNIPPETS = [
    ("frontend/js/step4-farmer.js", "MARKET_DEMO"),
    ("frontend/js/step4-farmer.js", "BUYER_MATCH_DEMO"),
    ("frontend/js/step4-farmer.js", "matchScore: 94"),
    ("frontend/js/step4-farmer.js", "SELL NOW"),
    ("frontend/js/config.js", "DEMO_DATA"),
    ("frontend/js/config.js", "Lasalgaon APMC"),
    ("frontend/js/main.js", "item.currentPrice"),
    ("frontend/index.html", "₹3,200"),
    ("frontend/index.html", "Lasalgaon APMC"),
]


def test_no_fabricated_market_snippets():
    failures = []
    for rel, snippet in FORBIDDEN_SNIPPETS:
        path = os.path.join(ROOT, *rel.split("/"))
        text = open(path, encoding="utf-8", errors="replace").read()
        if snippet in text:
            failures.append(f"{rel} still contains {snippet!r}")
    assert not failures, "\n".join(failures)


def test_farmer_forecast_is_api_driven():
    path = os.path.join(ROOT, "frontend", "js", "price-forecast.js")
    text = open(path, encoding="utf-8").read()
    assert "/api/forecast" in text
    assert "sale_window" in text
    assert "p10" in text.lower() or "price_low" in text
