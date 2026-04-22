"""
Metric Scorer — Implements the 19-metric scoring instrument (§6)
and evaluates the 5 experimental claims.

Scores all 19 metrics across three layers:
  - Layer 1 (M1–M5): Input — governance capability from GRD spec
  - Layer 2 (M6–M9): Process — governance mechanics from pipeline results
  - Layer 3 (M14–M19): Output — system properties from model analysis

M10–M13 are post-deployment metrics, marked PENDING until live data is available.
"""

from dataclasses import dataclass, field
from typing import Any, List, Dict

from grt_engine.config import GRDConfig
from grt_engine.proxy_detector import ProxyReport
from grt_engine.threshold_calibrator import CalibrationReport
from grt_engine.hci import HCIResult


@dataclass
class MetricScore:
    """Result of scoring a single metric."""
    metric_id: str          # "M1" through "M19"
    name: str
    layer: int              # 1, 2, or 3
    control_value: Any      # numeric or string
    treatment_value: Any
    verdict: str            # PASS, FAIL, PENDING, INCONCLUSIVE
    finding: str            # one-line summary


@dataclass
class ClaimVerdict:
    """Verdict for one of the five experimental claims."""
    claim_id: str           # "C1" through "C5"
    description: str
    verdict: str            # CONFIRMED, PARTIALLY_CONFIRMED, INCONCLUSIVE, PENDING
    primary_metrics: List[str]
    secondary_metrics: List[str]
    rationale: str


@dataclass
class MetricScorecard:
    """Complete scorecard: all 19 metric scores and 5 claim verdicts."""
    scores: List[MetricScore] = field(default_factory=list)
    claims: List[ClaimVerdict] = field(default_factory=list)

    def summary(self) -> str:
        """Human-readable summary of the scorecard."""
        lines = [
            '19-METRIC SCORECARD',
            '=' * 70,
            '',
            '{:<6} {:<35} {:>5} {:>12} {:>12} {:>12}'.format(
                'ID', 'Name', 'Layer', 'Control', 'Treatment', 'Verdict'),
            '-' * 70,
        ]
        for s in self.scores:
            lines.append('{:<6} {:<35} {:>5} {:>12} {:>12} {:>12}'.format(
                s.metric_id, s.name[:35], s.layer,
                str(s.control_value)[:12], str(s.treatment_value)[:12],
                s.verdict))
        lines.append('')
        lines.append('CLAIM VERDICTS')
        lines.append('=' * 70)
        lines.append('')
        for c in self.claims:
            lines.append('{} — {} → {}'.format(c.claim_id, c.description, c.verdict))
            lines.append('  Primary: {}'.format(', '.join(c.primary_metrics)))
            if c.secondary_metrics:
                lines.append('  Secondary: {}'.format(', '.join(c.secondary_metrics)))
            lines.append('  Rationale: {}'.format(c.rationale))
            lines.append('')
        return '\n'.join(lines)

    def to_dict(self) -> dict:
        """Serialize scorecard to a JSON-compatible dict."""
        return {
            'scores': [
                {
                    'metric_id': s.metric_id,
                    'name': s.name,
                    'layer': s.layer,
                    'control_value': s.control_value,
                    'treatment_value': s.treatment_value,
                    'verdict': s.verdict,
                    'finding': s.finding,
                }
                for s in self.scores
            ],
            'claims': [
                {
                    'claim_id': c.claim_id,
                    'description': c.description,
                    'verdict': c.verdict,
                    'primary_metrics': c.primary_metrics,
                    'secondary_metrics': c.secondary_metrics,
                    'rationale': c.rationale,
                }
                for c in self.claims
            ],
        }


# Metric-to-Claim mapping per METRICS.md
METRIC_TO_CLAIM_MAP: Dict[str, Dict[str, List[str]]] = {
    'C1': {'primary': ['M4', 'M6', 'M15'], 'secondary': []},
    'C2': {
        'primary': ['M1', 'M2', 'M7', 'M8', 'M9'],
        'secondary': ['M14', 'M16', 'M17', 'M18', 'M19'],
    },
    'C3': {'primary': ['M3'], 'secondary': []},
    'C4': {'primary': ['ALL'], 'secondary': []},
    'C5': {
        'primary': ['M1', 'M14', 'M15', 'M18'],
        'secondary': ['M10', 'M11', 'M12', 'M13'],
    },
}

# Claim descriptions
CLAIM_DESCRIPTIONS: Dict[str, str] = {
    'C1': 'Governance surfaces problems earlier',
    'C2': 'Governance changes the design',
    'C3': 'Governance changes deployment decision',
    'C4': 'Framework metrics produce real signal',
    'C5': 'Cost is worth it',
}


class MetricScorer:
    """
    Scores all 19 metrics and evaluates the 5 experimental claims.

    Layer 1 (M1–M5): Scored from GRD specification completeness.
    Layer 2 (M6–M9): Scored from pipeline results. M10–M13 PENDING.
    Layer 3 (M14–M19): Scored from control/treatment output params.
    """

    def __init__(self, config: GRDConfig):
        self.config = config

    def score_all(
        self,
        proxy_report: ProxyReport,
        calibration_report: CalibrationReport,
        control_hci: HCIResult,
        treatment_hci: HCIResult,
        control_params: dict,
        treatment_params: dict,
    ) -> MetricScorecard:
        """Score all 19 metrics and evaluate claims."""
        scores = []

        # --- Layer 1: Input (Governance Capability) ---
        scores.append(self._score_m1(control_params, treatment_params))
        scores.append(self._score_m2())
        scores.append(self._score_m3())
        scores.append(self._score_m4(proxy_report))
        scores.append(self._score_m5())

        # --- Layer 2: Process (Governance Mechanics) ---
        scores.append(self._score_m6(proxy_report))
        scores.append(self._score_m7(calibration_report))
        scores.append(self._score_m8(proxy_report))
        scores.append(self._score_m9())
        # M10–M13: post-deployment, always PENDING
        scores.append(self._pending_metric('M10', 'Drift Detection', 2))
        scores.append(self._pending_metric('M11', 'Override-Event Signal Quality', 2))
        scores.append(self._pending_metric('M12', 'Knowledge-Roster Coverage', 2))
        scores.append(self._pending_metric('M13', 'Frame-Refresh Cadence', 2))

        # --- Layer 3: Output (System Properties) ---
        scores.append(self._score_m14(control_params, treatment_params))
        scores.append(self._score_m15(control_params, treatment_params))
        scores.append(self._score_m16(control_params, treatment_params))
        scores.append(self._score_m17(control_params, treatment_params))
        scores.append(self._score_m18(control_params, treatment_params))
        scores.append(self._score_m19(control_params, treatment_params))

        claims = self.evaluate_claims(scores)
        return MetricScorecard(scores=scores, claims=claims)

    # ── Layer 1 scoring ──

    def _score_m1(self, control_params: dict, treatment_params: dict) -> MetricScore:
        """M1: Goal Definition Maturity (0–12).
        2 points each for: frame origin, residue declared, incentive mapped,
        non-goals specified, temporal condition, composability.
        """
        cfg = self.config
        treatment_score = 0
        if cfg.frame_author:
            treatment_score += 2  # frame origin
        if cfg.residue_domains:
            treatment_score += 2  # residue declared
        if cfg.cost_bearers or cfg.beneficiaries:
            treatment_score += 2  # incentive mapped
        if cfg.blocked_features:
            treatment_score += 2  # non-goals specified
        if cfg.data_vintage_start or cfg.staleness_months != 24:
            treatment_score += 2  # temporal condition
        if cfg.stakeholder_frames:
            treatment_score += 2  # composability

        # Control: minimal — typically 2/12 (bare goal, no governance)
        control_score = control_params.get('m1_score', 2)

        verdict = 'PASS' if treatment_score > control_score else 'FAIL'
        return MetricScore(
            metric_id='M1', name='Goal Definition Maturity', layer=1,
            control_value=control_score, treatment_value=treatment_score,
            verdict=verdict,
            finding='Treatment {}/12 vs Control {}/12'.format(
                treatment_score, control_score),
        )

    def _score_m2(self) -> MetricScore:
        """M2: Rule Specification (0–5 domains covered)."""
        cfg = self.config
        domains = 0
        if cfg.blocked_features:
            domains += 1  # proxy-blocking rules
        if cfg.thresholds:
            domains += 1  # threshold-routing rules
        if cfg.authority_routing:
            domains += 1  # authority routing rules
        if cfg.reason_weights:
            domains += 1  # reason weight rules
        if cfg.residue_domains:
            domains += 1  # non-goal guardrails

        control_val = 0
        verdict = 'PASS' if domains > control_val else 'FAIL'
        return MetricScore(
            metric_id='M2', name='Rule Specification', layer=1,
            control_value=control_val, treatment_value=domains,
            verdict=verdict,
            finding='Treatment covers {}/5 rule domains vs Control 0/5'.format(domains),
        )

    def _score_m3(self) -> MetricScore:
        """M3: Deployment-Level Decision (1–5)."""
        treatment_level = self.config.deployment_level
        control_level = 1  # default: build-and-ship
        verdict = 'PASS' if treatment_level > control_level else 'FAIL'
        return MetricScore(
            metric_id='M3', name='Deployment-Level Decision', layer=1,
            control_value=control_level, treatment_value=treatment_level,
            verdict=verdict,
            finding='Treatment Level {} vs Control Level {}'.format(
                treatment_level, control_level),
        )

    def _score_m4(self, proxy_report: ProxyReport) -> MetricScore:
        """M4: Proxy Detection (found/blocked counts)."""
        found = proxy_report.proxies_found
        blocked = proxy_report.proxies_blocked
        control_val = '0/{}'.format(found)
        treatment_val = '{}/{}'.format(blocked, found)
        verdict = 'PASS' if blocked >= found and found > 0 else (
            'FAIL' if found > 0 else 'INCONCLUSIVE')
        return MetricScore(
            metric_id='M4', name='Proxy Detection', layer=1,
            control_value=control_val, treatment_value=treatment_val,
            verdict=verdict,
            finding='Detected {} proxies, blocked {}'.format(found, blocked),
        )

    def _score_m5(self) -> MetricScore:
        """M5: Frame Mapping (0–10).
        Up to 5 for frame identification, up to 5 for coupling detection.
        """
        cfg = self.config
        frame_count = min(len(cfg.stakeholder_frames), 5)
        # Couplings: count authority_routing entries as cross-frame couplings
        coupling_count = min(len(cfg.authority_routing), 5)
        treatment_score = frame_count + coupling_count
        control_score = 0
        verdict = 'PASS' if treatment_score > control_score else 'FAIL'
        return MetricScore(
            metric_id='M5', name='Frame Mapping', layer=1,
            control_value=control_score, treatment_value=treatment_score,
            verdict=verdict,
            finding='Treatment {}/10 vs Control 0/10'.format(treatment_score),
        )

    # ── Layer 2 scoring ──

    def _score_m6(self, proxy_report: ProxyReport) -> MetricScore:
        """M6: Frame-Mismatch Flagging (pass/fail)."""
        enforcement = proxy_report.boundary_enforcement_rate
        treatment_pass = enforcement > 0
        verdict = 'PASS' if treatment_pass else 'FAIL'
        return MetricScore(
            metric_id='M6', name='Frame-Mismatch Flagging', layer=2,
            control_value='No flagging', treatment_value='{:.0%}'.format(enforcement),
            verdict=verdict,
            finding='Boundary enforcement rate: {:.0%}'.format(enforcement),
        )

    def _score_m7(self, calibration_report: CalibrationReport) -> MetricScore:
        """M7: Threshold Fire Patterns (pass if calibrated)."""
        calibrated = calibration_report.calibrated_count
        total = len(calibration_report.results)
        pending = calibration_report.pending_count
        non_pending = total - pending
        treatment_pass = calibrated == non_pending and non_pending > 0
        verdict = 'PASS' if treatment_pass else (
            'PENDING' if non_pending == 0 else 'FAIL')
        return MetricScore(
            metric_id='M7', name='Threshold Fire Patterns', layer=2,
            control_value='No thresholds',
            treatment_value='{}/{} calibrated'.format(calibrated, non_pending),
            verdict=verdict,
            finding='{} of {} non-pending thresholds calibrated'.format(
                calibrated, non_pending),
        )

    def _score_m8(self, proxy_report: ProxyReport) -> MetricScore:
        """M8: Boundary Enforcement (0–100%)."""
        rate = proxy_report.boundary_enforcement_rate
        control_val = 0.0  # no boundaries declared
        verdict = 'PASS' if rate > control_val else 'FAIL'
        return MetricScore(
            metric_id='M8', name='Boundary Enforcement', layer=2,
            control_value='{:.0%}'.format(control_val),
            treatment_value='{:.0%}'.format(rate),
            verdict=verdict,
            finding='Treatment {:.0%} boundary enforcement vs Control 0%'.format(rate),
        )

    def _score_m9(self) -> MetricScore:
        """M9: Authority Routing (pass/fail)."""
        has_routing = bool(self.config.authority_routing)
        verdict = 'PASS' if has_routing else 'FAIL'
        return MetricScore(
            metric_id='M9', name='Authority Routing', layer=2,
            control_value='Not defined',
            treatment_value='Defined' if has_routing else 'Not defined',
            verdict=verdict,
            finding='Authority routing {}'.format(
                'defined' if has_routing else 'not defined'),
        )

    # ── Layer 3 scoring ──

    def _score_m14(self, control_params: dict, treatment_params: dict) -> MetricScore:
        """M14: Bias Reduction (Disparate Impact Ratio)."""
        ctrl = control_params.get('disparate_impact_ratio', 0.0)
        treat = treatment_params.get('disparate_impact_ratio', 0.0)
        # Closer to 1.0 is better
        verdict = 'PASS' if abs(1.0 - treat) <= abs(1.0 - ctrl) else 'FAIL'
        return MetricScore(
            metric_id='M14', name='Bias Reduction', layer=3,
            control_value=ctrl, treatment_value=treat,
            verdict=verdict,
            finding='DIR Control {:.4f} vs Treatment {:.4f}'.format(ctrl, treat),
        )

    def _score_m15(self, control_params: dict, treatment_params: dict) -> MetricScore:
        """M15: Proxy Influence (percentage)."""
        ctrl = control_params.get('proxy_influence_pct', 0.0)
        treat = treatment_params.get('proxy_influence_pct', 0.0)
        # Lower is better
        verdict = 'PASS' if treat <= ctrl else 'FAIL'
        return MetricScore(
            metric_id='M15', name='Proxy Influence', layer=3,
            control_value='{:.1%}'.format(ctrl),
            treatment_value='{:.1%}'.format(treat),
            verdict=verdict,
            finding='Proxy influence Control {:.1%} vs Treatment {:.1%}'.format(
                ctrl, treat),
        )

    def _score_m16(self, control_params: dict, treatment_params: dict) -> MetricScore:
        """M16: Resilience under Disruption (pass/fail)."""
        ctrl = control_params.get('resilience_pass', False)
        treat = treatment_params.get('resilience_pass', False)
        verdict = 'PASS' if treat and not ctrl else (
            'PASS' if treat and ctrl else (
                'FAIL' if not treat else 'INCONCLUSIVE'))
        return MetricScore(
            metric_id='M16', name='Resilience under Disruption', layer=3,
            control_value='Pass' if ctrl else 'Fail',
            treatment_value='Pass' if treat else 'Fail',
            verdict=verdict,
            finding='Resilience Control={} Treatment={}'.format(
                'Pass' if ctrl else 'Fail', 'Pass' if treat else 'Fail'),
        )

    def _score_m17(self, control_params: dict, treatment_params: dict) -> MetricScore:
        """M17: Strategic-Alignment Preservation (pass/fail)."""
        ctrl = control_params.get('strategic_pass', False)
        treat = treatment_params.get('strategic_pass', False)
        verdict = 'PASS' if treat and not ctrl else (
            'PASS' if treat and ctrl else (
                'FAIL' if not treat else 'INCONCLUSIVE'))
        return MetricScore(
            metric_id='M17', name='Strategic-Alignment Preservation', layer=3,
            control_value='Pass' if ctrl else 'Fail',
            treatment_value='Pass' if treat else 'Fail',
            verdict=verdict,
            finding='Strategic alignment Control={} Treatment={}'.format(
                'Pass' if ctrl else 'Fail', 'Pass' if treat else 'Fail'),
        )

    def _score_m18(self, control_params: dict, treatment_params: dict) -> MetricScore:
        """M18: Frame Transparency (percentage)."""
        ctrl = control_params.get('frame_transparency_pct', 0.0)
        treat = treatment_params.get('frame_transparency_pct', 0.0)
        # Higher is better
        verdict = 'PASS' if treat > ctrl else 'FAIL'
        return MetricScore(
            metric_id='M18', name='Frame Transparency', layer=3,
            control_value='{:.0%}'.format(ctrl),
            treatment_value='{:.0%}'.format(treat),
            verdict=verdict,
            finding='Frame transparency Control {:.0%} vs Treatment {:.0%}'.format(
                ctrl, treat),
        )

    def _score_m19(self, control_params: dict, treatment_params: dict) -> MetricScore:
        """M19: Auditability (percentage)."""
        ctrl = control_params.get('auditability_pct', 0.0)
        treat = treatment_params.get('auditability_pct', 0.0)
        # Higher is better
        verdict = 'PASS' if treat > ctrl else 'FAIL'
        return MetricScore(
            metric_id='M19', name='Auditability', layer=3,
            control_value='{:.0%}'.format(ctrl),
            treatment_value='{:.0%}'.format(treat),
            verdict=verdict,
            finding='Auditability Control {:.0%} vs Treatment {:.0%}'.format(
                ctrl, treat),
        )

    # ── Helpers ──

    @staticmethod
    def _pending_metric(metric_id: str, name: str, layer: int) -> MetricScore:
        """Create a PENDING metric for post-deployment metrics (M10–M13)."""
        return MetricScore(
            metric_id=metric_id, name=name, layer=layer,
            control_value='N/A', treatment_value='N/A',
            verdict='PENDING',
            finding='Requires post-deployment data',
        )

    # ── Claim evaluation ──

    def evaluate_claims(self, scores: List[MetricScore]) -> List[ClaimVerdict]:
        """Evaluate the 5 experimental claims from metric scores."""
        score_map: Dict[str, MetricScore] = {s.metric_id: s for s in scores}
        claims = []

        for claim_id in ['C1', 'C2', 'C3', 'C4', 'C5']:
            mapping = METRIC_TO_CLAIM_MAP[claim_id]
            primary_ids = mapping['primary']
            secondary_ids = mapping['secondary']

            # Resolve primary metrics
            if primary_ids == ['ALL']:
                primary_scores = list(score_map.values())
                primary_ids_resolved = list(score_map.keys())
            else:
                primary_scores = [score_map[m] for m in primary_ids if m in score_map]
                primary_ids_resolved = primary_ids

            primary_verdicts = [s.verdict for s in primary_scores]

            # Determine claim verdict
            if any(v == 'PENDING' for v in primary_verdicts):
                verdict = 'PENDING'
                rationale = 'One or more primary metrics are PENDING (post-deployment data required)'
            elif all(v == 'PASS' for v in primary_verdicts):
                verdict = 'CONFIRMED'
                rationale = 'All primary metrics favor Treatment'
            elif any(v == 'PASS' for v in primary_verdicts):
                verdict = 'PARTIALLY_CONFIRMED'
                rationale = 'Directionally favorable but not all primary metrics pass'
            else:
                verdict = 'INCONCLUSIVE'
                rationale = 'Primary metrics do not favor Treatment'

            claims.append(ClaimVerdict(
                claim_id=claim_id,
                description=CLAIM_DESCRIPTIONS[claim_id],
                verdict=verdict,
                primary_metrics=primary_ids_resolved,
                secondary_metrics=secondary_ids,
                rationale=rationale,
            ))

        return claims
