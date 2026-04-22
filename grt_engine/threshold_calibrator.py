"""
Threshold Calibrator — Implements §4.4 (Stability and Threshold Tuning)
and §5.3 (Switched-System Analysis for Threshold Crossings).

Computes fire rates for each threshold, compares against target bands,
and maps miscalibrations to control-theoretic failure modes.
"""

from typing import Dict, List, Callable
from dataclasses import dataclass

from grt_engine.config import ThresholdSpec


@dataclass
class ThresholdResult:
    """Calibration result for a single threshold."""
    spec: ThresholdSpec
    fire_rate: float
    fire_count: int
    total_count: int
    status: str  # CALIBRATED, OVER, UNDER
    control_interpretation: str  # Laplace interpretation
    lyapunov_interpretation: str  # switched-system interpretation
    recalibration_action: str


@dataclass
class CalibrationReport:
    """Full threshold calibration report."""
    results: List[ThresholdResult]
    calibrated_count: int
    miscalibrated_count: int
    pending_count: int
    
    def summary(self) -> str:
        lines = [
            'THRESHOLD CALIBRATION REPORT',
            '=' * 60,
            'Calibrated:    {}'.format(self.calibrated_count),
            'Miscalibrated: {}'.format(self.miscalibrated_count),
            'Pending:       {}'.format(self.pending_count),
            '',
        ]
        for r in self.results:
            lines.append('  {} — fire rate: {:.1%} (target: {:.0%}–{:.0%}) → {}'.format(
                r.spec.name, r.fire_rate,
                r.spec.target_fire_rate[0], r.spec.target_fire_rate[1],
                r.status))
            lines.append('    Laplace:  {}'.format(r.control_interpretation))
            lines.append('    Lyapunov: {}'.format(r.lyapunov_interpretation))
            if r.recalibration_action:
                lines.append('    Action:   {}'.format(r.recalibration_action))
            lines.append('')
        return '\n'.join(lines)


class ThresholdCalibrator:
    """
    Evaluates threshold fire rates against target bands and
    produces control-theoretic interpretations of miscalibrations.
    """
    
    def calibrate(self, data, thresholds: List[ThresholdSpec],
                  threshold_functions: Dict[str, Callable]) -> CalibrationReport:
        """
        Run calibration for all thresholds.
        
        Args:
            data: pandas DataFrame
            thresholds: list of ThresholdSpec from GRD
            threshold_functions: dict mapping threshold name to a function
                that takes a DataFrame row and returns True if threshold fires
        """
        results = []
        
        for spec in thresholds:
            if spec.name not in threshold_functions:
                results.append(ThresholdResult(
                    spec=spec, fire_rate=0, fire_count=0,
                    total_count=len(data), status='PENDING',
                    control_interpretation='Cannot evaluate — no threshold function provided',
                    lyapunov_interpretation='Cannot evaluate',
                    recalibration_action='Define threshold function',
                ))
                continue
            
            func = threshold_functions[spec.name]
            fires = data.apply(func, axis=1)
            fire_count = fires.sum()
            fire_rate = fire_count / len(data) if len(data) > 0 else 0
            
            status = spec.is_calibrated(fire_rate)
            ctrl_interp = self._laplace_interpretation(spec, fire_rate)
            lyap_interp = self._lyapunov_interpretation(spec, fire_rate)
            action = self._recalibration_action(spec, fire_rate, status)
            
            results.append(ThresholdResult(
                spec=spec,
                fire_rate=fire_rate,
                fire_count=int(fire_count),
                total_count=len(data),
                status=status,
                control_interpretation=ctrl_interp,
                lyapunov_interpretation=lyap_interp,
                recalibration_action=action,
            ))
        
        cal = sum(1 for r in results if r.status == 'CALIBRATED')
        mis = sum(1 for r in results if 'OVER' in r.status or 'UNDER' in r.status)
        pen = sum(1 for r in results if r.status == 'PENDING')
        
        return CalibrationReport(
            results=results,
            calibrated_count=cal,
            miscalibrated_count=mis,
            pending_count=pen,
        )
    
    def _laplace_interpretation(self, spec: ThresholdSpec, fire_rate: float) -> str:
        lo, hi = spec.target_fire_rate
        if lo <= fire_rate <= hi:
            return 'Gain correctly tuned — threshold fires within design band (§4.4)'
        elif fire_rate > hi:
            if fire_rate > 0.8:
                return ('Gain saturation — controller always on, provides no '
                        'discrimination (§4.4 degenerate)')
            else:
                return ('Marginally stable — gain too high, threshold over-fires, '
                        'risk of oscillation (§4.4)')
        else:
            if fire_rate == 0:
                return ('Gain starvation — controller never activates, disturbance '
                        'undetected (§4.4 degenerate)')
            else:
                return ('Over-damped — gain too low, threshold under-fires, '
                        'sluggish governance response (§4.4)')
    
    def _lyapunov_interpretation(self, spec: ThresholdSpec, fire_rate: float) -> str:
        lo, hi = spec.target_fire_rate
        if lo <= fire_rate <= hi:
            return 'Regime boundary reachable and crossable — switched-system conditions satisfiable (§5.3)'
        elif fire_rate > hi:
            if fire_rate > 0.8:
                return 'System never leaves escalated regime — threshold boundary unreachable from below (§5.3 degenerate)'
            else:
                return 'Frequent regime switching — monitor for threshold thrashing, check dwell-time condition (§5.3)'
        else:
            if fire_rate == 0:
                return 'Regime boundary unreachable from current state space — no switching occurs (§5.3 degenerate)'
            else:
                return 'Rare regime switching — boundary exists but seldom crossed (§5.3)'
    
    def _recalibration_action(self, spec: ThresholdSpec, fire_rate: float, status: str) -> str:
        if status == 'CALIBRATED':
            return ''
        lo, hi = spec.target_fire_rate
        if fire_rate > hi:
            return 'Reduce threshold sensitivity (lower gain) to bring fire rate into {:.0%}–{:.0%} band'.format(lo, hi)
        elif fire_rate < lo:
            return 'Increase threshold sensitivity (raise gain) to bring fire rate into {:.0%}–{:.0%} band'.format(lo, hi)
        return ''
