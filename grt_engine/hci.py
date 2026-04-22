"""
Human Contribution Index (HCI) — Implements §6.

Computes H_F (frame contribution), H_D (decision contribution),
H_R (residue contribution), and the aggregate HCI using the
specified aggregator (geometric, arithmetic, or min).
"""

from dataclasses import dataclass
from typing import Dict, Optional

from grt_engine.config import HCISpec


@dataclass
class HCIResult:
    """HCI computation result."""
    h_f: float  # frame contribution
    h_d: float  # decision contribution
    h_r: float  # residue contribution
    hci_geometric: float
    hci_arithmetic: float
    hci_min: float
    hci_primary: float  # the one selected by spec
    aggregator: str
    
    # Sub-components for decomposition
    frame_authorship: float
    frame_documentation: float
    frame_challenge: float
    decision_position: str
    decision_position_value: float
    residue_surfacing: float
    residue_authorization: float
    residue_timeliness: float
    
    def summary(self) -> str:
        lines = [
            'HUMAN CONTRIBUTION INDEX',
            '=' * 50,
            '',
            'Frame Contribution (H_F):     {:.2f}'.format(self.h_f),
            '  authorship (a):             {:.2f}'.format(self.frame_authorship),
            '  documentation (d):          {:.2f}'.format(self.frame_documentation),
            '  challenge (c):              {:.2f}'.format(self.frame_challenge),
            '',
            'Decision Contribution (H_D):  {:.2f}'.format(self.h_d),
            '  position:                   {} ({:.2f})'.format(
                self.decision_position, self.decision_position_value),
            '',
            'Residue Contribution (H_R):   {:.2f}'.format(self.h_r),
            '  surfacing (s):              {:.2f}'.format(self.residue_surfacing),
            '  authorization (a):          {:.2f}'.format(self.residue_authorization),
            '  timeliness (t):             {:.2f}'.format(self.residue_timeliness),
            '',
            'HCI (geometric):              {:.3f}'.format(self.hci_geometric),
            'HCI (arithmetic):             {:.3f}'.format(self.hci_arithmetic),
            'HCI (min):                    {:.3f}'.format(self.hci_min),
            '',
            'Primary ({}):          {:.3f}'.format(self.aggregator, self.hci_primary),
        ]
        return '\n'.join(lines)


class HCICalculator:
    """
    Computes HCI from governance configuration parameters.
    
    This is the measurement instrument — it takes a description of
    how a system is governed and produces the HCI score with full
    decomposition.
    """
    
    def __init__(self, spec: Optional[HCISpec] = None):
        self.spec = spec or HCISpec()
    
    def compute(self,
                # Frame Origin components
                frame_authorship: float = 0.0,  # 0 or 1
                frame_documentation: float = 0.0,  # 0 to 1
                frame_challenge: float = 0.0,  # 0 or 1
                # Decision Authority
                decision_position: str = 'none',
                authority_weights: Optional[Dict[str, float]] = None,
                # Residue Declaration
                residue_surfacing: float = 0.0,  # 0 to 1
                residue_authorization: float = 0.0,  # 0 to 1
                residue_timeliness: float = 0.0,  # 0 to 1
                ) -> HCIResult:
        """Compute HCI with full decomposition."""
        
        # H_F: Frame Contribution (§6.3.1)
        w1, w2, w3 = self.spec.hf_weights
        h_f = w1 * frame_authorship + w2 * frame_documentation + w3 * frame_challenge
        
        # H_D: Decision Contribution (§6.3.2)
        pos_value = self.spec.hd_positions.get(decision_position, 0.0)
        h_d = pos_value
        
        # If distributed authority, use weighted maximum
        if authority_weights:
            weighted_positions = []
            for party, alpha in authority_weights.items():
                party_pos = self.spec.hd_positions.get(party, 0.0)
                weighted_positions.append(alpha * party_pos)
            if weighted_positions:
                h_d = max(weighted_positions)
        
        # H_R: Residue Contribution (§6.3.3)
        w1r, w2r, w3r = self.spec.hr_weights
        h_r = w1r * residue_surfacing + w2r * residue_authorization + w3r * residue_timeliness
        
        # Aggregate
        hci_geo = (h_f * h_d * h_r) ** (1/3) if (h_f > 0 and h_d > 0 and h_r > 0) else 0.0
        hci_arith = (h_f + h_d + h_r) / 3
        hci_min = min(h_f, h_d, h_r)
        
        primary_map = {
            'geometric': hci_geo,
            'arithmetic': hci_arith,
            'min': hci_min,
        }
        hci_primary = primary_map.get(self.spec.aggregator, hci_geo)
        
        return HCIResult(
            h_f=h_f, h_d=h_d, h_r=h_r,
            hci_geometric=hci_geo,
            hci_arithmetic=hci_arith,
            hci_min=hci_min,
            hci_primary=hci_primary,
            aggregator=self.spec.aggregator,
            frame_authorship=frame_authorship,
            frame_documentation=frame_documentation,
            frame_challenge=frame_challenge,
            decision_position=decision_position,
            decision_position_value=pos_value,
            residue_surfacing=residue_surfacing,
            residue_authorization=residue_authorization,
            residue_timeliness=residue_timeliness,
        )
    
    def compare(self, results: Dict[str, HCIResult]) -> str:
        """Compare HCI across multiple systems."""
        lines = ['HCI COMPARISON', '=' * 60, '']
        header = '{:<25} {:>6} {:>6} {:>6} {:>8}'.format(
            'System', 'H_F', 'H_D', 'H_R', 'HCI')
        lines.append(header)
        lines.append('-' * 60)
        for name, r in results.items():
            lines.append('{:<25} {:>6.2f} {:>6.2f} {:>6.2f} {:>8.3f}'.format(
                name, r.h_f, r.h_d, r.h_r, r.hci_primary))
        return '\n'.join(lines)
