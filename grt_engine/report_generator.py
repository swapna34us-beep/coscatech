"""
Report Generator — Produces text and JSON reports from GRT analysis results.

Generates human-readable text reports and machine-readable JSON reports
with all numeric values, verdicts, control-theoretic interpretations,
and metadata for downstream consumption.
"""

import json

from grt_engine.engine import AnalysisReport
from grt_engine.metric_scorer import MetricScorecard
from grt_engine.hci import HCICalculator


class ReportGenerator:
    """Generates text and JSON reports from analysis results."""

    @staticmethod
    def generate_text(report: AnalysisReport,
                      scorecard: MetricScorecard) -> str:
        """Generate human-readable text report with all sections.

        Sections:
          1. Proxy detection summary
          2. Threshold calibration with Laplace/Lyapunov interpretations
          3. HCI comparison table
          4. 19-metric scorecard (Control/Treatment/Verdict)
          5. Claim verdicts with supporting metrics
        """
        lines: list[str] = []

        # Header
        lines.append('=' * 70)
        lines.append('  GRT ANALYSIS REPORT')
        lines.append('  GRD: {}'.format(report.config.name))
        lines.append('  Generated: {}'.format(report.timestamp))
        lines.append('=' * 70)
        lines.append('')

        # ── Section 1: Proxy Detection Summary ──
        lines.append('PROXY DETECTION SUMMARY')
        lines.append('-' * 70)
        if report.proxy_report:
            pr = report.proxy_report
            lines.append('Candidates scanned:   {}'.format(pr.total_candidates))
            lines.append('Proxies found:        {}'.format(pr.proxies_found))
            lines.append('Proxies blocked:      {}'.format(pr.proxies_blocked))
            lines.append('Proxy influence:      {:.1%}'.format(pr.proxy_influence_pct))
            lines.append('Boundary enforcement: {:.0%}'.format(
                pr.boundary_enforcement_rate))
            lines.append('')
            for r in pr.results:
                status = ('BLOCKED' if r.blocked
                          else ('PROXY' if r.is_proxy else 'clean'))
                lines.append('  {} <-> {}: r={:.3f} (p={:.4f}) [{}]'.format(
                    r.feature, r.protected_attribute,
                    r.correlation, r.p_value, status))
        else:
            lines.append('No proxy detection results available.')
        lines.append('')

        # ── Section 2: Threshold Calibration ──
        lines.append('THRESHOLD CALIBRATION')
        lines.append('-' * 70)
        if report.calibration_report:
            cr = report.calibration_report
            lines.append('Calibrated:    {}'.format(cr.calibrated_count))
            lines.append('Miscalibrated: {}'.format(cr.miscalibrated_count))
            lines.append('Pending:       {}'.format(cr.pending_count))
            lines.append('')
            for r in cr.results:
                lines.append('  {} — fire rate: {:.1%} (target: {:.0%}-{:.0%}) -> {}'.format(
                    r.spec.name, r.fire_rate,
                    r.spec.target_fire_rate[0], r.spec.target_fire_rate[1],
                    r.status))
                lines.append('    Laplace:  {}'.format(r.control_interpretation))
                lines.append('    Lyapunov: {}'.format(r.lyapunov_interpretation))
                if r.recalibration_action:
                    lines.append('    Action:   {}'.format(r.recalibration_action))
                lines.append('')
        else:
            lines.append('No threshold calibration results available.')
            lines.append('')

        # ── Section 3: HCI Comparison Table ──
        lines.append('HCI COMPARISON')
        lines.append('-' * 70)
        if report.hci_results:
            calc = HCICalculator(report.config.hci_spec)
            lines.append(calc.compare(report.hci_results))
        else:
            lines.append('No HCI results available.')
        lines.append('')

        # ── Section 4: 19-Metric Scorecard ──
        lines.append('19-METRIC SCORECARD')
        lines.append('-' * 70)
        lines.append('{:<6} {:<35} {:>5} {:>12} {:>12} {:>12}'.format(
            'ID', 'Name', 'Layer', 'Control', 'Treatment', 'Verdict'))
        lines.append('-' * 70)
        for s in scorecard.scores:
            lines.append('{:<6} {:<35} {:>5} {:>12} {:>12} {:>12}'.format(
                s.metric_id, s.name[:35], s.layer,
                str(s.control_value)[:12],
                str(s.treatment_value)[:12],
                s.verdict))
        lines.append('')

        # ── Section 5: Claim Verdicts ──
        lines.append('CLAIM VERDICTS')
        lines.append('-' * 70)
        for c in scorecard.claims:
            lines.append('{} — {} -> {}'.format(
                c.claim_id, c.description, c.verdict))
            lines.append('  Primary metrics:   {}'.format(
                ', '.join(c.primary_metrics)))
            if c.secondary_metrics:
                lines.append('  Secondary metrics: {}'.format(
                    ', '.join(c.secondary_metrics)))
            lines.append('  Rationale: {}'.format(c.rationale))
            lines.append('')

        return '\n'.join(lines)

    @staticmethod
    def generate_json(report: AnalysisReport,
                      scorecard: MetricScorecard) -> dict:
        """Generate machine-readable JSON report.

        Includes all numeric values, verdicts, interpretations, and
        metadata (GRD name, timestamp, row count).
        """
        # Derive row count from calibration results or dataset metadata
        row_count = 0
        if (report.calibration_report
                and report.calibration_report.results):
            row_count = report.calibration_report.results[0].total_count
        elif report.config.dataset_metadata.get('row_count'):
            row_count = report.config.dataset_metadata['row_count']

        result: dict = {
            'metadata': {
                'grd_name': report.config.name,
                'timestamp': report.timestamp,
                'row_count': row_count,
            },
            'proxy_detection': ReportGenerator._proxy_to_dict(report),
            'threshold_calibration': ReportGenerator._calibration_to_dict(report),
            'hci': ReportGenerator._hci_to_dict(report),
            'scorecard': scorecard.to_dict(),
        }
        return result

    @staticmethod
    def serialize_json(report_dict: dict) -> str:
        """Serialize to JSON string with sorted keys and 2-space indent.

        Round-trip stable: json.loads(serialize_json(d)) re-serialized
        via serialize_json() produces byte-identical output.
        """
        return json.dumps(report_dict, sort_keys=True, indent=2)

    # ── Private helpers ──

    @staticmethod
    def _proxy_to_dict(report: AnalysisReport) -> dict:
        pr = report.proxy_report
        if not pr:
            return {
                'boundary_enforcement_rate': 0.0,
                'proxies_blocked': 0,
                'proxies_found': 0,
                'proxy_influence_pct': 0.0,
                'results': [],
                'total_candidates': 0,
            }
        return {
            'boundary_enforcement_rate': pr.boundary_enforcement_rate,
            'proxies_blocked': pr.proxies_blocked,
            'proxies_found': pr.proxies_found,
            'proxy_influence_pct': pr.proxy_influence_pct,
            'results': [
                {
                    'blocked': r.blocked,
                    'correlation': r.correlation,
                    'feature': r.feature,
                    'is_proxy': r.is_proxy,
                    'p_value': r.p_value,
                    'protected_attribute': r.protected_attribute,
                }
                for r in pr.results
            ],
            'total_candidates': pr.total_candidates,
        }

    @staticmethod
    def _calibration_to_dict(report: AnalysisReport) -> dict:
        cr = report.calibration_report
        if not cr:
            return {
                'calibrated_count': 0,
                'miscalibrated_count': 0,
                'pending_count': 0,
                'results': [],
            }
        return {
            'calibrated_count': cr.calibrated_count,
            'miscalibrated_count': cr.miscalibrated_count,
            'pending_count': cr.pending_count,
            'results': [
                {
                    'fire_count': r.fire_count,
                    'fire_rate': r.fire_rate,
                    'laplace_interpretation': r.control_interpretation,
                    'lyapunov_interpretation': r.lyapunov_interpretation,
                    'name': r.spec.name,
                    'recalibration_action': r.recalibration_action,
                    'status': r.status,
                    'target_fire_rate': list(r.spec.target_fire_rate),
                    'total_count': r.total_count,
                }
                for r in cr.results
            ],
        }

    @staticmethod
    def _hci_to_dict(report: AnalysisReport) -> dict:
        if not report.hci_results:
            return {}
        return {
            name: {
                'aggregator': r.aggregator,
                'h_d': r.h_d,
                'h_f': r.h_f,
                'h_r': r.h_r,
                'hci_arithmetic': r.hci_arithmetic,
                'hci_geometric': r.hci_geometric,
                'hci_min': r.hci_min,
                'hci_primary': r.hci_primary,
            }
            for name, r in report.hci_results.items()
        }
