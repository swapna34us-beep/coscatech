#!/usr/bin/env python3
"""Aggregate procurement transactions into supplier-category profiles.

Usage:
    python scripts/aggregate_profiles.py procurement_data_full_v4.csv > supplier_profiles.json
"""

import csv
import json
import sys
from collections import Counter, defaultdict


def parse_bool(val: str) -> bool:
    return val.strip().lower() in ("true", "1", "yes")


def parse_float(val: str) -> float:
    return float(val.strip())


def mode_bool(values: list[bool]) -> bool:
    """Return the most frequent boolean value (mode)."""
    counts = Counter(values)
    return counts.most_common(1)[0][0]


def aggregate(csv_path: str) -> list[dict]:
    """Read CSV and return aggregated supplier-category profiles."""
    # Group rows by (supplier_id, category)
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row["supplier_id"], row["category"])
            groups[key].append(row)

    # Compute total spend per category (for category_spend_share)
    category_total_spend: dict[str, float] = defaultdict(float)
    for (_, cat), rows in groups.items():
        for r in rows:
            category_total_spend[cat] += parse_float(r["total_dollars_obligated"])

    profiles = []
    for (supplier_id, category), rows in groups.items():
        n = len(rows)

        # Carry-forward fields (same for all rows in group)
        first = rows[0]
        supplier_name = first["supplier_name"]
        supplier_tier = first["supplier_tier"]
        supplier_employee_count = int(first["supplier_employee_count"])
        supplier_hq_region = first["supplier_hq_region"]
        supplier_founding_year = int(first["supplier_founding_year"])

        # Averages for numeric scoring fields
        avg_unit_price = sum(parse_float(r["unit_price"]) for r in rows) / n
        avg_volume = sum(parse_float(r["volume"]) for r in rows) / n
        avg_total_dollars_obligated = sum(parse_float(r["total_dollars_obligated"]) for r in rows) / n
        avg_on_time_delivery_pct = sum(parse_float(r["on_time_delivery_pct"]) for r in rows) / n
        avg_quality_score = sum(parse_float(r["quality_score"]) for r in rows) / n

        # is_cost_reduction_era_pct: mean of boolean
        is_cost_reduction_era_pct = sum(1 for r in rows if parse_bool(r["is_cost_reduction_era"])) / n

        # transaction_count
        transaction_count = n

        # last_transaction_date: max date string (ISO format sorts lexicographically)
        last_transaction_date = max(r["transaction_date"].strip() for r in rows)

        # Boolean hidden fields: mode
        diversity_certified = mode_bool([parse_bool(r["diversity_certified"]) for r in rows])
        strategic_alignment = mode_bool([parse_bool(r["strategic_alignment"]) for r in rows])

        # Numeric hidden fields: averages
        avg_relationship_years = sum(parse_float(r["relationship_years"]) for r in rows) / n
        avg_buyer_trust_score = sum(parse_float(r["buyer_trust_score"]) for r in rows) / n
        avg_disruption_resilience = sum(parse_float(r["disruption_resilience"]) for r in rows) / n

        # category_spend_share
        supplier_cat_spend = sum(parse_float(r["total_dollars_obligated"]) for r in rows)
        category_spend_share = supplier_cat_spend / category_total_spend[category] if category_total_spend[category] > 0 else 0.0

        profiles.append({
            "supplier_id": supplier_id,
            "supplier_name": supplier_name,
            "supplier_tier": supplier_tier,
            "supplier_employee_count": supplier_employee_count,
            "supplier_hq_region": supplier_hq_region,
            "supplier_founding_year": supplier_founding_year,
            "category": category,
            "avg_unit_price": round(avg_unit_price, 2),
            "avg_volume": round(avg_volume, 2),
            "avg_total_dollars_obligated": round(avg_total_dollars_obligated, 2),
            "avg_on_time_delivery_pct": round(avg_on_time_delivery_pct, 2),
            "avg_quality_score": round(avg_quality_score, 2),
            "is_cost_reduction_era_pct": round(is_cost_reduction_era_pct, 4),
            "transaction_count": transaction_count,
            "last_transaction_date": last_transaction_date,
            "diversity_certified": diversity_certified,
            "avg_relationship_years": round(avg_relationship_years, 2),
            "avg_buyer_trust_score": round(avg_buyer_trust_score, 2),
            "avg_disruption_resilience": round(avg_disruption_resilience, 2),
            "strategic_alignment": strategic_alignment,
            "category_spend_share": round(category_spend_share, 6),
        })

    # Sort for deterministic output
    profiles.sort(key=lambda p: (p["supplier_id"], p["category"]))
    return profiles


def main():
    if len(sys.argv) < 2:
        print("Usage: python aggregate_profiles.py <csv_path>", file=sys.stderr)
        sys.exit(1)

    csv_path = sys.argv[1]
    profiles = aggregate(csv_path)
    print(json.dumps(profiles, indent=2))


if __name__ == "__main__":
    main()
