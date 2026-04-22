"""
GRT Engine — Main orchestrator.

Runs the full GRT governance analysis pipeline:
  1. Load dataset + GRD config
  2. Proxy detection (§3.2, M4, M6, M15)
  3. Threshold calibration (§4.4, §5.3)
  4. HCI computation (§6)
  5. Control vs Treatment comparison
  6. Report generation with control-theoretic interpretations
"""

import json
from datetime import datetime
from typing import Dict, List, Optional, Callable

from grt_engine.config import GRDConfig
from grt_engine.proxy_detector import ProxyDetector, ProxyReport
from grt_engine.threshold_calibrator import ThresholdCalibrator, CalibrationReport
from grt_engine.hci import HCICalculator, HCIResult
from grt_engine.grd_loader import GRDLoader
from grt_engine.schema_normalizer import SchemaNormalizer
from grt_engine.metric_scorer import MetricScorer, MetricScorecard


class PipelineError(Exception):
    """Raised when a pipeline stage fails."""

    def __init__(self, stage: str, cause: Exception):
        self.stage = stage
        self.cause = cause
        super().__init__(f"Pipeline failed at stage '{stage}': {cause}")


class GRTEngine:
    """
    Main engine for running GRT governance analysis.

    Usage:
        config = GRDConfig(
            name='My Governance Analysis',
            target_column='predicted_value',
            protected_attributes=['race', 'gender'],
            proxy_candidates=['zip_code', 'school_name'],
            ...
        )
        engine = GRTEngine(config)
        engine.load_dataset('data.csv')
        results = engine.run_full_analysis()
        print(results.summary())
    """

    def __init__(self, config: GRDConfig):
        self.config = config
        self.data = None
        self.proxy_report: Optional[ProxyReport] = None
        self.calibration_report: Optional[CalibrationReport] = None
        self.hci_results: Dict[str, HCIResult] = {}
        self._threshold_functions: Dict[str, Callable] = {}
        self.scorecard: Optional[MetricScorecard] = None
        self._raw_grd: Optional[dict] = None

    def load_dataset(self, path: str):
        """Load dataset from CSV."""
        import pandas as pd
        self.data = pd.read_csv(path)
        print('Loaded {} rows, {} columns from {}'.format(
            len(self.data), len(self.data.columns), path))
        return self

    def load_dataframe(self, df):
        """Load dataset from an existing DataFrame."""
        self.data = df.copy()
        print('Loaded {} rows, {} columns'.format(len(self.data), len(self.data.columns)))
        return self

    def register_threshold(self, name: str, func: Callable):
        """Register a threshold function. func(row) -> bool."""
        self._threshold_functions[name] = func
        return self

    # ── GRD Loading ──

    def load_grd(self, path: str) -> GRDConfig:
        """Load GRD JSON via GRDLoader, set self.config.

        Also stores the raw GRD dict for use by verify_dataset().
        """
        raw = json.loads(open(path, encoding='utf-8').read())
        self._raw_grd = raw
        self.config = GRDLoader.load(path)
        return self.config

    # ── Schema Normalization ──

    def normalize_schema(self):
        """Normalize loaded dataset via SchemaNormalizer.

        Returns the normalized DataFrame (also updates self.data in place).
        """
        if self.data is None:
            raise ValueError('No dataset loaded. Call load_dataset() first.')
        self.data = SchemaNormalizer.normalize(self.data)
        return self.data

    # ── Stage 1: Proxy Detection ──

    def run_proxy_detection(self, feature_importances: Optional[Dict[str, float]] = None) -> ProxyReport:
        """Run proxy detection across all candidate features."""
        if self.data is None:
            raise ValueError('No dataset loaded. Call load_dataset() first.')

        detector = ProxyDetector(self.config.proxy_correlation_threshold)

        # Determine feature columns to scan
        feature_cols = self.config.proxy_candidates or [
            c for c in self.data.columns
            if c != self.config.target_column
            and c not in self.config.protected_attributes
        ]

        self.proxy_report = detector.detect(
            data=self.data,
            feature_cols=feature_cols,
            protected_cols=self.config.protected_attributes,
            blocked_cols=self.config.blocked_features,
            feature_importances=feature_importances,
        )

        return self.proxy_report

    # ── Stage 2: Threshold Calibration ──

    def run_threshold_calibration(self) -> CalibrationReport:
        """Run threshold calibration against target bands."""
        if self.data is None:
            raise ValueError('No dataset loaded.')

        calibrator = ThresholdCalibrator()
        self.calibration_report = calibrator.calibrate(
            data=self.data,
            thresholds=self.config.thresholds,
            threshold_functions=self._threshold_functions,
        )

        return self.calibration_report

    # ── Stage 3: HCI Computation ──

    def compute_hci(self, system_name: str, **kwargs) -> HCIResult:
        """Compute HCI for a named system configuration."""
        calculator = HCICalculator(self.config.hci_spec)
        result = calculator.compute(**kwargs)
        self.hci_results[system_name] = result
        return result

    # ── Dataset Verification ──

    def verify_dataset(self, tolerance: float = 0.08) -> List[str]:
        """Run dataset integrity checks. Return list of warnings.

        Checks:
          1. Row count 9500-10500
          2. GRD-referenced columns exist
          3. Proxy correlations within tolerance of GRD targets
          4. Reason weights keys present
          5. T3 fire rate check
        """
        from scipy.stats import pointbiserialr
        import pandas as pd

        if self.data is None:
            raise ValueError('No dataset loaded.')

        warnings: List[str] = []
        df = self.data

        # 1. Row count check
        n = len(df)
        if not (9500 <= n <= 10500):
            warnings.append(
                'Row count {} outside expected range 9500-10500'.format(n)
            )

        # 2. GRD-referenced columns exist
        grd_errors = SchemaNormalizer.validate_against_grd(df, self.config)
        warnings.extend(grd_errors)

        # 3. Proxy correlations within tolerance of GRD targets
        proxy_targets = {}
        if self._raw_grd:
            for entry in self._raw_grd.get('proxy_exclusion_list', []):
                feature = entry.get('feature', '')
                r_target = entry.get('r_target')
                if feature and r_target is not None:
                    proxy_targets[feature] = r_target

        if proxy_targets and 'diversity_certified' in df.columns:
            region_map = {
                'Northeast': 0, 'Southeast': 1, 'Midwest': 2,
                'West': 3, 'Southwest': 4, 'Pacific': 5,
            }
            div = df['diversity_certified'].astype(int).values

            for feature, target_r in proxy_targets.items():
                if feature not in df.columns:
                    continue
                vals = df[feature].values
                if feature == 'supplier_hq_region' and vals.dtype == object:
                    vals = pd.Series(vals).map(region_map).values.astype(float)
                else:
                    vals = vals.astype(float)

                r, _ = pointbiserialr(vals, div)
                deviation = abs(r - target_r)
                if deviation > tolerance:
                    warnings.append(
                        'Proxy correlation {}: observed r={:.3f}, '
                        'target r={:.3f}, deviation {:.3f} exceeds '
                        'tolerance {:.3f}'.format(
                            feature, r, target_r, deviation, tolerance
                        )
                    )

        # 4. Reason weights keys present
        if self._raw_grd:
            rw = self._raw_grd.get('reason_weights', {})
            required_reasons = ['Strategic', 'Relationship', 'Resilience', 'Price']
            missing_r = [r for r in required_reasons if r not in rw]
            if missing_r:
                warnings.append(
                    'GRD reason_weights missing keys: {}'.format(missing_r)
                )

        # 5. T3 fire rate check
        if 'total_dollars_obligated' in df.columns:
            t3_rate = (df['total_dollars_obligated'] > 500000).mean()
            if not (0.15 <= t3_rate <= 0.55):
                warnings.append(
                    'T3 fire rate {:.1%} outside expected range 15%-55%'.format(
                        t3_rate
                    )
                )

        return warnings

    # ── Metric Scoring ──

    def score_metrics(self, control_params: dict,
                      treatment_params: dict) -> MetricScorecard:
        """Score all 19 metrics and evaluate claims via MetricScorer.

        Requires proxy_report to be computed first.
        """
        if self.proxy_report is None:
            raise ValueError('No proxy report. Run run_proxy_detection() first.')

        scorer = MetricScorer(self.config)

        control_hci = self.hci_results.get('Control')
        treatment_hci = self.hci_results.get('Treatment')

        if control_hci is None or treatment_hci is None:
            hci_values = list(self.hci_results.values())
            if len(hci_values) >= 2:
                control_hci = hci_values[0]
                treatment_hci = hci_values[1]
            else:
                calc = HCICalculator(self.config.hci_spec)
                control_hci = control_hci or calc.compute()
                treatment_hci = treatment_hci or calc.compute()

        calibration = self.calibration_report or CalibrationReport(
            results=[], calibrated_count=0, miscalibrated_count=0, pending_count=0
        )

        self.scorecard = scorer.score_all(
            proxy_report=self.proxy_report,
            calibration_report=calibration,
            control_hci=control_hci,
            treatment_hci=treatment_hci,
            control_params=control_params,
            treatment_params=treatment_params,
        )
        return self.scorecard

    # ── Report Generation ──

    def generate_report(self, format: str = 'text') -> str:
        """Generate report via ReportGenerator.

        Args:
            format: 'text' for human-readable, 'json' for machine-readable.

        Returns:
            Report string (text or JSON).
        """
        from grt_engine.report_generator import ReportGenerator

        if self.proxy_report is None:
            raise ValueError('No analysis results. Run the pipeline first.')

        report = AnalysisReport(
            config=self.config,
            proxy_report=self.proxy_report,
            calibration_report=self.calibration_report,
            hci_results=self.hci_results,
            timestamp=datetime.now().isoformat(),
        )

        scorecard = self.scorecard or MetricScorecard()

        if format == 'json':
            report_dict = ReportGenerator.generate_json(report, scorecard)
            return ReportGenerator.serialize_json(
                _convert_numpy_types(report_dict)
            )
        else:
            return ReportGenerator.generate_text(report, scorecard)

    # ── Stage 4: Full Analysis ──

    def run_full_analysis(self,
                          feature_importances: Optional[Dict[str, float]] = None,
                          control_params: Optional[dict] = None,
                          treatment_params: Optional[dict] = None,
                          ) -> 'AnalysisReport':
        """Run the complete GRT analysis pipeline.

        Stages:
          0. Schema normalization
          1. Proxy detection
          2. Threshold calibration
          3. HCI computation
          4. Metric scoring
        """
        print()
        print('=' * 60)
        print('  GRT ENGINE — Full Governance Analysis')
        print('  GRD: {}'.format(self.config.name))
        print('=' * 60)
        print()

        # Schema normalization
        try:
            print('Stage 0: Schema Normalization...')
            self.normalize_schema()
            print('  Normalized to {} columns'.format(len(self.data.columns)))
        except Exception as e:
            raise PipelineError('schema_normalization', e)

        # Proxy detection
        try:
            print('Stage 1: Proxy Detection...')
            proxy = self.run_proxy_detection(feature_importances)
            print('  Found {}/{} proxies, {} blocked'.format(
                proxy.proxies_found, proxy.total_candidates, proxy.proxies_blocked))
        except Exception as e:
            raise PipelineError('proxy_detection', e)

        # Threshold calibration
        try:
            if self.config.thresholds and self._threshold_functions:
                print('Stage 2: Threshold Calibration...')
                cal = self.run_threshold_calibration()
                print('  {} calibrated, {} miscalibrated, {} pending'.format(
                    cal.calibrated_count, cal.miscalibrated_count, cal.pending_count))
            else:
                print('Stage 2: Threshold Calibration — skipped (no thresholds defined)')
                cal = None
        except Exception as e:
            raise PipelineError('threshold_calibration', e)

        # HCI
        try:
            print('Stage 3: HCI Computation...')
            if self.hci_results:
                for name, result in self.hci_results.items():
                    print('  {}: HCI = {:.3f}'.format(name, result.hci_primary))
            else:
                print('  No HCI configurations registered. Call compute_hci() first.')
        except Exception as e:
            raise PipelineError('hci_computation', e)

        # Metric scoring
        try:
            if control_params is not None and treatment_params is not None:
                print('Stage 4: Metric Scoring...')
                self.score_metrics(control_params, treatment_params)
                pass_count = sum(
                    1 for s in self.scorecard.scores if s.verdict == 'PASS'
                )
                print('  Scored 19 metrics: {} PASS'.format(pass_count))
            else:
                print('Stage 4: Metric Scoring — skipped (no control/treatment params)')
        except Exception as e:
            raise PipelineError('metric_scoring', e)

        print()
        print('Analysis complete.')
        print()

        return AnalysisReport(
            config=self.config,
            proxy_report=proxy,
            calibration_report=cal,
            hci_results=self.hci_results,
            timestamp=datetime.now().isoformat(),
        )


class AnalysisReport:
    """Complete GRT analysis report."""

    def __init__(self, config, proxy_report, calibration_report, hci_results, timestamp):
        self.config = config
        self.proxy_report = proxy_report
        self.calibration_report = calibration_report
        self.hci_results = hci_results
        self.timestamp = timestamp

    def summary(self) -> str:
        lines = [
            '',
            '═' * 60,
            '  GRT ANALYSIS REPORT',
            '  GRD: {}'.format(self.config.name),
            '  Generated: {}'.format(self.timestamp),
            '═' * 60,
            '',
        ]

        if self.proxy_report:
            lines.append(self.proxy_report.summary())
            lines.append('')

        if self.calibration_report:
            lines.append(self.calibration_report.summary())
            lines.append('')

        if self.hci_results:
            calc = HCICalculator(self.config.hci_spec)
            lines.append(calc.compare(self.hci_results))
            lines.append('')

        return '\n'.join(lines)

    def to_json(self, path: str):
        """Export report as JSON for reproducibility."""
        report = {
            'grd_name': self.config.name,
            'timestamp': self.timestamp,
            'proxy_detection': {
                'proxies_found': self.proxy_report.proxies_found if self.proxy_report else 0,
                'proxies_blocked': self.proxy_report.proxies_blocked if self.proxy_report else 0,
                'boundary_enforcement': self.proxy_report.boundary_enforcement_rate if self.proxy_report else 0,
                'proxy_influence_pct': self.proxy_report.proxy_influence_pct if self.proxy_report else 0,
            },
            'threshold_calibration': {
                'calibrated': self.calibration_report.calibrated_count if self.calibration_report else 0,
                'miscalibrated': self.calibration_report.miscalibrated_count if self.calibration_report else 0,
                'thresholds': [
                    {
                        'name': r.spec.name,
                        'fire_rate': r.fire_rate,
                        'target': list(r.spec.target_fire_rate),
                        'status': r.status,
                        'laplace': r.control_interpretation,
                        'lyapunov': r.lyapunov_interpretation,
                    }
                    for r in (self.calibration_report.results if self.calibration_report else [])
                ],
            },
            'hci': {
                name: {
                    'h_f': r.h_f, 'h_d': r.h_d, 'h_r': r.h_r,
                    'hci_geometric': r.hci_geometric,
                    'hci_arithmetic': r.hci_arithmetic,
                    'hci_min': r.hci_min,
                }
                for name, r in self.hci_results.items()
            },
        }
        with open(path, 'w') as f:
            json.dump(report, f, indent=2)
        print('Report saved to {}'.format(path))


def _convert_numpy_types(obj):
    """Recursively convert numpy types to native Python types for JSON serialization."""
    import numpy as np
    if isinstance(obj, dict):
        return {k: _convert_numpy_types(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_numpy_types(v) for v in obj]
    elif isinstance(obj, (np.integer,)):
        return int(obj)
    elif isinstance(obj, (np.floating,)):
        return float(obj)
    elif isinstance(obj, (np.bool_,)):
        return bool(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj
