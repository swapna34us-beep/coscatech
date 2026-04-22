"""
Proxy Detector — Implements Residue Declaration (§3.2) and
Corruption Surface Coverage (M4) computationally.

Detects features that correlate with protected attributes above
the declared threshold, flags them as proxy pathways, and
computes boundary enforcement metrics.
"""

import numpy as np
from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class ProxyResult:
    """Result of proxy detection for a single feature-attribute pair."""
    feature: str
    protected_attribute: str
    correlation: float
    p_value: float
    is_proxy: bool
    blocked: bool


@dataclass
class ProxyReport:
    """Full proxy detection report."""
    results: List[ProxyResult]
    total_candidates: int
    proxies_found: int
    proxies_blocked: int
    proxy_influence_pct: float  # total feature importance of proxy features
    boundary_enforcement_rate: float  # M6: % of proxies blocked
    
    def summary(self) -> str:
        lines = [
            'PROXY DETECTION REPORT',
            '=' * 50,
            'Candidates scanned:  {}'.format(self.total_candidates),
            'Proxies found:       {}/{}'.format(self.proxies_found, self.total_candidates),
            'Proxies blocked:     {}/{}'.format(self.proxies_blocked, self.proxies_found),
            'Proxy influence:     {:.1%}'.format(self.proxy_influence_pct),
            'Boundary enforcement: {:.0%} (M6)'.format(self.boundary_enforcement_rate),
            '',
        ]
        for r in self.results:
            status = 'BLOCKED' if r.blocked else ('PROXY' if r.is_proxy else 'clean')
            lines.append('  {} ↔ {}: r={:.3f} (p={:.4f}) [{}]'.format(
                r.feature, r.protected_attribute, r.correlation, r.p_value, status))
        return '\n'.join(lines)


class ProxyDetector:
    """
    Detects proxy features that correlate with protected attributes.
    
    This implements the computational version of what the GRT process
    does manually: scan every feature for correlation with every
    protected attribute, flag those above threshold, block them.
    """
    
    def __init__(self, correlation_threshold: float = 0.05):
        self.threshold = correlation_threshold
    
    def detect(self, data, feature_cols: List[str],
               protected_cols: List[str],
               blocked_cols: Optional[List[str]] = None,
               feature_importances: Optional[Dict[str, float]] = None
               ) -> ProxyReport:
        """
        Run proxy detection.
        
        Args:
            data: pandas DataFrame
            feature_cols: columns to scan as potential proxies
            protected_cols: protected attribute columns
            blocked_cols: features already blocked by governance
            feature_importances: dict of feature -> importance weight
        """
        from scipy import stats
        
        blocked = set(blocked_cols or [])
        importances = feature_importances or {}
        results = []
        
        for feat in feature_cols:
            for prot in protected_cols:
                # Skip if either column is missing
                if feat not in data.columns or prot not in data.columns:
                    continue
                
                # Get numeric representations
                feat_vals = self._to_numeric(data[feat])
                prot_vals = self._to_numeric(data[prot])
                
                if feat_vals is None or prot_vals is None:
                    continue
                
                # Drop NaN pairs
                mask = ~(np.isnan(feat_vals) | np.isnan(prot_vals))
                if mask.sum() < 30:
                    continue
                
                r, p = stats.pearsonr(feat_vals[mask], prot_vals[mask])
                
                is_proxy = abs(r) >= self.threshold and p < 0.05
                is_blocked = feat in blocked
                
                results.append(ProxyResult(
                    feature=feat,
                    protected_attribute=prot,
                    correlation=r,
                    p_value=p,
                    is_proxy=is_proxy,
                    blocked=is_blocked,
                ))
        
        proxies = [r for r in results if r.is_proxy]
        blocked_proxies = [r for r in proxies if r.blocked]
        
        # Compute proxy influence
        proxy_features = set(r.feature for r in proxies if not r.blocked)
        proxy_influence = sum(importances.get(f, 0) for f in proxy_features)
        
        enforcement = len(blocked_proxies) / len(proxies) if proxies else 1.0
        
        return ProxyReport(
            results=results,
            total_candidates=len(feature_cols) * len(protected_cols),
            proxies_found=len(proxies),
            proxies_blocked=len(blocked_proxies),
            proxy_influence_pct=proxy_influence,
            boundary_enforcement_rate=enforcement,
        )
    
    def _to_numeric(self, series):
        """Convert a pandas series to numeric, encoding categoricals."""
        import pandas as pd
        if pd.api.types.is_numeric_dtype(series):
            return series.values.astype(float)
        try:
            codes = series.astype('category').cat.codes
            return codes.values.astype(float)
        except Exception:
            return None
