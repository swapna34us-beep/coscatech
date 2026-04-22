"""
GRT Configuration — Governance Rule Document (GRD) as code.

A GRDConfig encodes the six principles as computational parameters:
  - Frame Origin: protected_attributes, target_column, frame_author, frame_date
  - Residue Declaration: proxy_correlation_threshold, proxy_candidates
  - Permanent Incompleteness: edge_case_detection_method, escalation_channel
  - Distributed Epistemic Authority: authority_weights, observation_filters
  - Temporal Honesty: data_vintage_window, staleness_threshold
  - Incentive Mapping: cost_bearers, beneficiaries, party_weights
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ThresholdSpec:
    """A single governance threshold with target calibration band."""
    name: str
    description: str
    target_fire_rate: Tuple[float, float]  # (low, high) target band
    knowledge_owner: str  # who has authority when threshold fires
    threshold_type: str = 'epistemic'  # 'epistemic' or 'metric'
    value: Optional[float] = None  # the actual threshold value
    
    def is_calibrated(self, actual_fire_rate: float) -> str:
        lo, hi = self.target_fire_rate
        if lo <= actual_fire_rate <= hi:
            return 'CALIBRATED'
        elif actual_fire_rate < lo:
            return 'UNDER'
        else:
            return 'OVER'


@dataclass
class HCISpec:
    """HCI measurement specification."""
    aggregator: str = 'geometric'  # 'geometric', 'arithmetic', 'min'
    hf_weights: Tuple[float, float, float] = (1/3, 1/3, 1/3)  # a, d, c
    hr_weights: Tuple[float, float, float] = (1/3, 1/3, 1/3)  # s, a, t
    hd_positions: Dict[str, float] = field(default_factory=lambda: {
        'pre_execution': 1.00,
        'rt_active': 0.75,
        'rt_on_demand': 0.50,
        'post_execution_review': 0.25,
        'post_hoc_audit': 0.10,
        'none': 0.00,
    })


@dataclass
class GRDConfig:
    """
    Governance Rule Document — the complete governance specification.
    This is §3's six principles encoded as a computational config.
    """
    # ── Frame Origin (§3.1) ──
    name: str = 'Unnamed GRD'
    frame_author: str = ''
    frame_date: str = ''
    frame_expiry: str = ''
    frame_challenge_procedure: bool = False
    target_column: str = ''
    protected_attributes: List[str] = field(default_factory=list)
    
    # ── Residue Declaration (§3.2) ──
    proxy_candidates: List[str] = field(default_factory=list)
    proxy_correlation_threshold: float = 0.05  # |r| above this = proxy
    residue_domains: List[str] = field(default_factory=list)
    
    # ── Permanent Incompleteness (§3.3) ──
    edge_case_method: str = 'confidence_interval'  # how to detect edge cases
    escalation_channel: str = 'flag_and_route'
    
    # ── Distributed Epistemic Authority (§3.4) ──
    stakeholder_frames: List[str] = field(default_factory=list)
    authority_weights: Dict[str, float] = field(default_factory=dict)
    
    # ── Temporal Honesty (§3.5) ──
    data_vintage_start: str = ''  # earliest acceptable data date
    staleness_months: int = 24  # months before a component is stale
    
    # ── Incentive Mapping (§3.6) ──
    cost_bearers: Dict[str, str] = field(default_factory=dict)
    beneficiaries: Dict[str, str] = field(default_factory=dict)
    party_weights: Dict[str, float] = field(default_factory=dict)
    
    # ── Distributed Epistemic Authority — Routing (§3.4) ──
    authority_routing: Dict[str, Dict[str, str]] = field(default_factory=dict)
    
    # ── Deployment ──
    deployment_level: int = 1
    
    # ── Reason Weights ──
    reason_weights: Dict[str, float] = field(default_factory=dict)
    
    # ── Era Bias Configuration ──
    era_bias_config: Dict[str, Any] = field(default_factory=dict)
    
    # ── Dataset Metadata ──
    dataset_metadata: Dict[str, Any] = field(default_factory=dict)
    
    # ── Thresholds ──
    thresholds: List[ThresholdSpec] = field(default_factory=list)
    
    # ── HCI Specification ──
    hci_spec: HCISpec = field(default_factory=HCISpec)
    
    # ── Dataset ──
    feature_columns: List[str] = field(default_factory=list)
    blocked_features: List[str] = field(default_factory=list)
