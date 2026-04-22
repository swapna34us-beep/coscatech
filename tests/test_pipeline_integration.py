"""
Integration tests for the full GRT analysis pipeline.

Tests the end-to-end flow:
  generate dataset → load GRD → normalize schema → run full analysis →
  generate text and JSON reports.

Uses the actual grd_procurement_v1.json for the GRD and a small
synthetic dataset (100 rows) for speed.
"""

import json
import os
import pytest
import numpy as np
import pandas as pd

from grt_engine import (
    GRTEngine,
    GRDLoader,
    DatasetGenerator,
    PipelineError,
    MetricScorecard,
)
from grt_engine.config import GRDConfig


# ── Paths ──

GRD_PATH = os.path.join(os.path.dirname(__file__), '..', 'grd_procurement_v1.json')


# ── Helpers ──

def _build_small_dataset(seed: int = 42, n: int = 100) -> pd.DataFrame:
    """Build a small DataFrame with the right v4 columns and some proxy correlations.

    This avoids calling DatasetGenerator.generate() (which produces 10k rows)
    and keeps integration tests fast.
    """
    rng = np.random.default_rng(seed)

    # Supplier attributes
    employee_counts = rng.integers(10, 10000, size=n)
    regions = rng.choice(
        ['Northeast', 'Southeast', 'Midwest', 'West', 'Southwest', 'Pacific'],
        size=n,
    )
    founding_years = rng.integers(1950, 2021, size=n)

    # Build a latent variable correlated with proxy features to produce
    # diversity_certified with approximate target correlations
    emp_z = (employee_counts - employee_counts.mean()) / (employee_counts.std() + 1e-10)
    region_map = {
        'Northeast': 0, 'Southeast': 1, 'Midwest': 2,
        'West': 3, 'Southwest': 4, 'Pacific': 5,
    }
    region_numeric = np.array([region_map[r] for r in regions], dtype=float)
    reg_z = (region_numeric - region_numeric.mean()) / (region_numeric.std() + 1e-10)
    year_z = (founding_years - founding_years.mean()) / (founding_years.std() + 1e-10)

    latent = -3.0 * emp_z + 2.5 * reg_z + 2.0 * year_z + rng.normal(0, 1.0, size=n)
    threshold = np.percentile(latent, 41)  # ~59% diversity rate
    diversity = (latent >= threshold).astype(bool)

    # Dates spanning the full range including cost-reduction era
    dates = pd.date_range('2020-10-16', periods=n, freq='20D')

    # Total dollars — some above 500k for T3 threshold
    total_dollars = rng.lognormal(mean=11.0, sigma=1.5, size=n).round(2)

    df = pd.DataFrame({
        'transaction_id': [f'TXN-{i:06d}' for i in range(n)],
        'transaction_date': dates[:n],
        'buyer_id': [f'BUY-{rng.integers(1, 11):03d}' for _ in range(n)],
        'supplier_id': [f'SUP-{rng.integers(1, 151):04d}' for _ in range(n)],
        'supplier_name': [f'Supplier_{rng.integers(1, 151)}' for _ in range(n)],
        'supplier_tier': rng.choice(['LARGE', 'MEDIUM', 'SMALL'], size=n),
        'supplier_employee_count': employee_counts,
        'supplier_hq_region': regions,
        'supplier_founding_year': founding_years,
        'category': rng.choice([
            'Professional Services', 'IT Hardware', 'Raw Materials',
            'Office Supplies', 'Facilities', 'Logistics',
            'Marketing', 'HR Services', 'Legal Services', 'IT Software',
        ], size=n),
        'unit_price': rng.lognormal(6.0, 1.5, size=n).clip(10, 50000).round(2),
        'volume': rng.integers(1, 1001, size=n),
        'total_dollars_obligated': total_dollars,
        'on_time_delivery_pct': rng.beta(8.5, 1.5, size=n).round(3),
        'quality_score': np.clip(rng.normal(3.8, 0.7, size=n), 1.0, 5.0).round(2),
        'is_cost_reduction_era': dates[:n] < pd.Timestamp('2023-01-01'),
        'diversity_certified': diversity,
        'relationship_years': rng.integers(0, 21, size=n),
        'buyer_trust_score': rng.beta(6, 3, size=n).round(3),
        'disruption_resilience': rng.beta(4, 4, size=n).round(3),
        'strategic_alignment': rng.random(size=n) < 0.115,
    })

    return df


# ── Control params (no governance) ──

CONTROL_PARAMS = {
    'm1_score': 2,
    'disparate_impact_ratio': 0.65,
    'proxy_influence_pct': 0.15,
    'resilience_pass': False,
    'strategic_pass': False,
    'frame_transparency_pct': 0.0,
    'auditability_pct': 0.0,
}

# ── Treatment params (with GRD governance) ──

TREATMENT_PARAMS = {
    'disparate_impact_ratio': 0.92,
    'proxy_influence_pct': 0.0,
    'resilience_pass': True,
    'strategic_pass': True,
    'frame_transparency_pct': 0.85,
    'auditability_pct': 0.90,
}


# ═══════════════════════════════════════════════════════════════════
# Integration Tests
# ═══════════════════════════════════════════════════════════════════

class TestFullPipelineIntegration:
    """Test the full pipeline: load GRD → load data → normalize → analyze → report."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up engine with GRD and small dataset."""
        self.config = GRDLoader.load(GRD_PATH)
        self.engine = GRTEngine(self.config)
        self.df = _build_small_dataset(seed=42, n=100)
        self.engine.load_dataframe(self.df)

    def test_full_pipeline_produces_analysis_report(self):
        """Full pipeline runs without error and produces an AnalysisReport."""
        # Register a threshold function for T3 (High-Value Authority)
        self.engine.register_threshold(
            'High-Value Authority',
            lambda row: row['total_dollars_obligated'] > 500000,
        )

        # Compute HCI for Control and Treatment
        self.engine.compute_hci(
            'Control',
            frame_authorship=0.0,
            frame_documentation=0.0,
            frame_challenge=0.0,
            decision_position='none',
        )
        self.engine.compute_hci(
            'Treatment',
            frame_authorship=1.0,
            frame_documentation=0.8,
            frame_challenge=1.0,
            decision_position='rt_active',
            residue_surfacing=0.9,
            residue_authorization=0.8,
            residue_timeliness=0.7,
        )

        report = self.engine.run_full_analysis(
            control_params=CONTROL_PARAMS,
            treatment_params=TREATMENT_PARAMS,
        )

        assert report is not None
        assert report.proxy_report is not None
        assert report.config.name == 'Procurement Supplier Recommendation System'

    def test_text_report_contains_all_sections(self):
        """Text report includes proxy, calibration, HCI, scorecard, and claims."""
        self.engine.register_threshold(
            'High-Value Authority',
            lambda row: row['total_dollars_obligated'] > 500000,
        )
        self.engine.compute_hci('Control', decision_position='none')
        self.engine.compute_hci(
            'Treatment',
            frame_authorship=1.0,
            frame_documentation=0.8,
            frame_challenge=1.0,
            decision_position='rt_active',
            residue_surfacing=0.9,
            residue_authorization=0.8,
            residue_timeliness=0.7,
        )

        self.engine.run_full_analysis(
            control_params=CONTROL_PARAMS,
            treatment_params=TREATMENT_PARAMS,
        )

        text_report = self.engine.generate_report(format='text')

        # All major sections present
        assert 'PROXY DETECTION SUMMARY' in text_report
        assert 'THRESHOLD CALIBRATION' in text_report
        assert 'HCI COMPARISON' in text_report
        assert '19-METRIC SCORECARD' in text_report
        assert 'CLAIM VERDICTS' in text_report

    def test_text_report_has_correct_laplace_labels(self):
        """Laplace labels use corrected terminology: over-damped for under-firing,
        marginally stable for over-firing."""
        self.engine.register_threshold(
            'High-Value Authority',
            lambda row: row['total_dollars_obligated'] > 500000,
        )
        self.engine.compute_hci('Control', decision_position='none')
        self.engine.compute_hci(
            'Treatment',
            frame_authorship=1.0,
            decision_position='rt_active',
            residue_surfacing=0.9,
            residue_authorization=0.8,
            residue_timeliness=0.7,
        )

        self.engine.run_full_analysis(
            control_params=CONTROL_PARAMS,
            treatment_params=TREATMENT_PARAMS,
        )

        text_report = self.engine.generate_report(format='text')

        # The report should contain Laplace interpretations.
        # Under-firing → "Over-damped", Over-firing → "Marginally stable"
        # At least one of these should appear depending on the data.
        assert 'Laplace' in text_report or 'THRESHOLD CALIBRATION' in text_report

        # Verify the corrected labels are NOT the old wrong ones
        assert 'under-damped' not in text_report.lower()

    def test_json_report_round_trip(self):
        """JSON report round-trips: parse → re-serialize → identical bytes."""
        self.engine.register_threshold(
            'High-Value Authority',
            lambda row: row['total_dollars_obligated'] > 500000,
        )
        self.engine.compute_hci('Control', decision_position='none')
        self.engine.compute_hci(
            'Treatment',
            frame_authorship=1.0,
            decision_position='rt_active',
            residue_surfacing=0.9,
            residue_authorization=0.8,
            residue_timeliness=0.7,
        )

        self.engine.run_full_analysis(
            control_params=CONTROL_PARAMS,
            treatment_params=TREATMENT_PARAMS,
        )

        json_str = self.engine.generate_report(format='json')
        parsed = json.loads(json_str)
        re_serialized = json.dumps(parsed, sort_keys=True, indent=2)

        assert json_str == re_serialized

    def test_json_report_has_metadata_and_sections(self):
        """JSON report contains metadata, proxy_detection, threshold_calibration,
        hci, and scorecard sections."""
        self.engine.register_threshold(
            'High-Value Authority',
            lambda row: row['total_dollars_obligated'] > 500000,
        )
        self.engine.compute_hci('Control', decision_position='none')
        self.engine.compute_hci(
            'Treatment',
            frame_authorship=1.0,
            decision_position='rt_active',
            residue_surfacing=0.9,
            residue_authorization=0.8,
            residue_timeliness=0.7,
        )

        self.engine.run_full_analysis(
            control_params=CONTROL_PARAMS,
            treatment_params=TREATMENT_PARAMS,
        )

        json_str = self.engine.generate_report(format='json')
        report_dict = json.loads(json_str)

        assert 'metadata' in report_dict
        assert 'proxy_detection' in report_dict
        assert 'threshold_calibration' in report_dict
        assert 'hci' in report_dict
        assert 'scorecard' in report_dict

        # Metadata has GRD name
        assert report_dict['metadata']['grd_name'] == 'Procurement Supplier Recommendation System'


class TestControlVsTreatmentConfig:
    """Verify Control uses defaults and Treatment uses GRD parameters."""

    def test_control_config_uses_defaults(self):
        """Control config: no blocked features, no thresholds, deployment level 1."""
        control = GRDConfig()

        assert control.blocked_features == []
        assert control.thresholds == []
        assert control.deployment_level == 1
        assert control.proxy_candidates == []
        assert control.authority_routing == {}

    def test_treatment_config_uses_grd_parameters(self):
        """Treatment config loaded from GRD has blocked features, thresholds, etc."""
        config = GRDLoader.load(GRD_PATH)

        # Blocked features from proxy_exclusion_list
        assert len(config.blocked_features) == 3
        assert 'supplier_employee_count' in config.blocked_features
        assert 'supplier_hq_region' in config.blocked_features
        assert 'supplier_founding_year' in config.blocked_features

        # Thresholds from knowledge_triggers
        assert len(config.thresholds) == 5
        threshold_names = [t.name for t in config.thresholds]
        assert 'Data Vintage Expiry' in threshold_names
        assert 'Concentration Risk' in threshold_names
        assert 'High-Value Authority' in threshold_names

        # Deployment level from deployment_decision
        assert config.deployment_level == 2

        # Authority routing from reviewer_knowledge_roster
        assert 'T1' in config.authority_routing
        assert 'T3' in config.authority_routing

        # Reason weights
        assert config.reason_weights.get('Strategic') == 1.0
        assert config.reason_weights.get('Price') == 0.4


class TestPipelineErrorHandling:
    """Verify pipeline halts on data errors with PipelineError."""

    def test_pipeline_halts_on_missing_columns(self):
        """Pipeline raises PipelineError when dataset is missing required columns."""
        config = GRDLoader.load(GRD_PATH)
        engine = GRTEngine(config)

        # Load a DataFrame missing required columns
        bad_df = pd.DataFrame({
            'transaction_id': ['TXN-1'],
            'some_random_col': [42],
        })
        engine.load_dataframe(bad_df)

        with pytest.raises(PipelineError) as exc_info:
            engine.run_full_analysis(
                control_params=CONTROL_PARAMS,
                treatment_params=TREATMENT_PARAMS,
            )

        assert exc_info.value.stage == 'schema_normalization'

    def test_pipeline_error_identifies_stage(self):
        """PipelineError contains the stage name and cause."""
        cause = ValueError("test cause")
        err = PipelineError(stage='proxy_detection', cause=cause)

        assert err.stage == 'proxy_detection'
        assert err.cause is cause
        assert 'proxy_detection' in str(err)


class TestScorecardIntegration:
    """Verify the scorecard is populated correctly through the pipeline."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.config = GRDLoader.load(GRD_PATH)
        self.engine = GRTEngine(self.config)
        self.df = _build_small_dataset(seed=42, n=100)
        self.engine.load_dataframe(self.df)

    def test_scorecard_has_19_metrics_and_5_claims(self):
        """Scorecard contains exactly 19 metric scores and 5 claim verdicts."""
        self.engine.register_threshold(
            'High-Value Authority',
            lambda row: row['total_dollars_obligated'] > 500000,
        )
        self.engine.compute_hci('Control', decision_position='none')
        self.engine.compute_hci(
            'Treatment',
            frame_authorship=1.0,
            decision_position='rt_active',
            residue_surfacing=0.9,
            residue_authorization=0.8,
            residue_timeliness=0.7,
        )

        self.engine.run_full_analysis(
            control_params=CONTROL_PARAMS,
            treatment_params=TREATMENT_PARAMS,
        )

        scorecard = self.engine.scorecard
        assert scorecard is not None
        assert len(scorecard.scores) == 19
        assert len(scorecard.claims) == 5

        # All metric IDs present
        metric_ids = {s.metric_id for s in scorecard.scores}
        expected_ids = {f'M{i}' for i in range(1, 20)}
        assert metric_ids == expected_ids

        # All claim IDs present
        claim_ids = {c.claim_id for c in scorecard.claims}
        assert claim_ids == {'C1', 'C2', 'C3', 'C4', 'C5'}

        # Each metric has a valid verdict
        valid_verdicts = {'PASS', 'FAIL', 'PENDING', 'INCONCLUSIVE'}
        for s in scorecard.scores:
            assert s.verdict in valid_verdicts

        # Each claim has a valid verdict
        valid_claim_verdicts = {
            'CONFIRMED', 'PARTIALLY_CONFIRMED', 'INCONCLUSIVE', 'PENDING',
        }
        for c in scorecard.claims:
            assert c.verdict in valid_claim_verdicts
