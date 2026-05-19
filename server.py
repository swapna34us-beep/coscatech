"""
GRT Dashboard Server.

Exposes the static dashboard and an `/api/run` endpoint that re-runs the
GRT engine with user-supplied target threshold bands and returns a fresh
analysis report.

Run with:
    python server.py
Then open http://127.0.0.1:5050/ in a browser.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, Tuple

from flask import Flask, jsonify, request, send_from_directory

from grt_engine import DatasetGenerator, GRTEngine
from grt_engine.config import GRDConfig, HCISpec, ThresholdSpec


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
VISIBLE_CSV = DATA_DIR / "procurement_visible.csv"
FULL_CSV = DATA_DIR / "procurement_full.csv"
REPORT_PATH = ROOT / "grt_analysis_report.json"

# Serialized access to engine runs — pandas + numpy are not thread-safe for
# this kind of workload, and running two engines in parallel doubles memory.
_engine_lock = threading.Lock()


# ── Defaults that mirror GRD.thresholds in grt_dashboard.html ────────────
# (id, name, target band, knowledge owner)
DEFAULT_THRESHOLDS: Tuple[Dict[str, Any], ...] = (
    {"id": "T1", "name": "Data Vintage Expiry",        "band": (0.10, 0.25), "owner": "senior_buyer"},
    {"id": "T2", "name": "Concentration Risk",         "band": (0.10, 0.20), "owner": "portfolio_owner"},
    {"id": "T3", "name": "High-Value Authority",       "band": (0.15, 0.22), "owner": "finance_controller"},
    {"id": "T4", "name": "Confidence Floor",           "band": (0.08, 0.15), "owner": "category_buyer"},
    {"id": "T5", "name": "Override Pattern Detection", "band": (0.05, 0.10), "owner": "governance_team"},
)

PROXY_FEATURES = [
    "supplier_employee_count",
    "supplier_hq_region",
    "supplier_founding_year",
]

# Control / Treatment parameters used by metric_scorer for the 19-metric
# scorecard. These mirror the values shown in the dashboard's static fallback.
CONTROL_PARAMS: Dict[str, Any] = {
    "m1_score": 2,
    "disparate_impact_ratio": 0.9681,
    "proxy_influence_pct": 0.032,
    "resilience_pass": False,
    "strategic_pass": False,
    "frame_transparency_pct": 0.28,
    "auditability_pct": 0.0,
}

TREATMENT_PARAMS: Dict[str, Any] = {
    "m1_score": 10,
    "disparate_impact_ratio": 0.9692,
    "proxy_influence_pct": 0.0,
    "resilience_pass": True,
    "strategic_pass": True,
    "frame_transparency_pct": 0.82,
    "auditability_pct": 0.90,
}


app = Flask(__name__, static_folder=str(ROOT), static_url_path="")


# ── Dataset / config helpers ─────────────────────────────────────────────


def ensure_dataset() -> None:
    """Generate the 10k-row procurement dataset on disk if it is missing."""
    if FULL_CSV.exists() and VISIBLE_CSV.exists():
        return
    print("[server] Generating procurement dataset (10k rows)...")
    gen = DatasetGenerator(seed=42)
    full_df, visible_df = gen.generate()
    gen.save(full_df, visible_df, str(FULL_CSV), str(VISIBLE_CSV))
    print(f"[server] Dataset cached at {FULL_CSV}")


def _clamp_band(low: float, high: float) -> Tuple[float, float]:
    low = max(0.0, min(1.0, float(low)))
    high = max(0.0, min(1.0, float(high)))
    if low > high:
        low, high = high, low
    return low, high


def build_config(thresholds_input: Dict[str, Dict[str, float]]) -> GRDConfig:
    """Build a GRDConfig with user-supplied target threshold bands."""
    specs = []
    for default in DEFAULT_THRESHOLDS:
        override = thresholds_input.get(default["id"]) or {}
        low = override.get("low", default["band"][0])
        high = override.get("high", default["band"][1])
        low, high = _clamp_band(low, high)
        specs.append(
            ThresholdSpec(
                name=default["name"],
                description=default["name"],
                target_fire_rate=(low, high),
                knowledge_owner=default["owner"],
            )
        )

    return GRDConfig(
        name="Procurement Supplier Recommendation System",
        target_column="diversity_certified",
        protected_attributes=["diversity_certified"],
        proxy_candidates=PROXY_FEATURES,
        blocked_features=PROXY_FEATURES,
        proxy_correlation_threshold=0.05,
        thresholds=specs,
        deployment_level=2,
        reason_weights={
            "Strategic": 1.0,
            "Relationship": 0.7,
            "Resilience": 0.6,
            "Price": 0.4,
        },
        hci_spec=HCISpec(),
    )


def run_engine_with_thresholds(thresholds_input: Dict[str, Dict[str, float]]) -> str:
    """Run the full GRT analysis pipeline; return the JSON report string."""
    import pandas as pd

    ensure_dataset()
    config = build_config(thresholds_input)

    engine = GRTEngine(config)
    df = pd.read_csv(FULL_CSV)
    engine.load_dataframe(df)

    # Register concrete threshold functions where the dataset supports them.
    # The other three thresholds remain PENDING (no function defined), which
    # mirrors the existing engine behaviour.
    engine.register_threshold(
        "High-Value Authority",
        lambda row: row["total_dollars_obligated"] > 500_000,
    )

    engine.compute_hci("Control", decision_position="none")
    engine.compute_hci(
        "Treatment",
        frame_authorship=1.0,
        frame_documentation=0.8,
        frame_challenge=1.0,
        decision_position="rt_active",
        residue_surfacing=0.9,
        residue_authorization=0.8,
        residue_timeliness=0.7,
    )

    engine.run_full_analysis(
        control_params=CONTROL_PARAMS,
        treatment_params=TREATMENT_PARAMS,
    )

    report_json = engine.generate_report(format="json")
    REPORT_PATH.write_text(report_json, encoding="utf-8")
    return report_json


# ── Routes ───────────────────────────────────────────────────────────────


@app.route("/")
def index():
    return send_from_directory(str(ROOT), "grt_dashboard.html")


@app.route("/grt_analysis_report.json")
def static_report():
    return send_from_directory(str(ROOT), "grt_analysis_report.json")


@app.route("/api/run", methods=["POST"])
def api_run():
    payload = request.get_json(silent=True) or {}
    thresholds_input = payload.get("thresholds") or {}

    try:
        with _engine_lock:
            report_json = run_engine_with_thresholds(thresholds_input)
    except Exception as exc:  # surface engine errors to the dashboard
        app.logger.exception("Engine run failed")
        return jsonify({"error": str(exc)}), 500

    return app.response_class(report_json, mimetype="application/json")


@app.route("/api/defaults", methods=["GET"])
def api_defaults():
    return jsonify(
        {
            "thresholds": [
                {"id": t["id"], "name": t["name"], "band": list(t["band"])}
                for t in DEFAULT_THRESHOLDS
            ]
        }
    )


if __name__ == "__main__":
    ensure_dataset()
    app.run(host="127.0.0.1", port=5050, debug=False)
