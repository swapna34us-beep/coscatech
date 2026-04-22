"""
Dataset Generator — produces synthetic procurement datasets with embedded
proxy correlations and era biases for GRT-HCI experiments.

Replaces the stub generate_procurement_data.py with a working implementation.
Generates:
  - full_df:    10,000 rows × 21 columns (v4 full schema)
  - visible_df: 10,000 rows × 16 columns (v4 visible schema)

Proxy correlations enforced via latent-variable thresholding:
  supplier_employee_count ↔ diversity_certified: r ≈ −0.58
  supplier_hq_region      ↔ diversity_certified: r ≈ +0.47
  supplier_founding_year  ↔ diversity_certified: r ≈ +0.39

Usage:
    gen = DatasetGenerator(seed=42)
    full_df, visible_df = gen.generate()
    gen.save(full_df, visible_df, 'full.csv', 'visible.csv')
"""

import numpy as np
import pandas as pd
from scipy.stats import pointbiserialr


class CorrelationEnforcementError(Exception):
    """Raised when proxy correlation enforcement fails to converge."""

    def __init__(self, achieved: dict, targets: dict):
        self.achieved = achieved
        self.targets = targets
        super().__init__(
            f"Proxy correlation enforcement failed to converge. "
            f"Achieved: {achieved}, Targets: {targets}"
        )


# ── Constants ──

CATEGORIES = [
    'Professional Services', 'IT Hardware', 'Raw Materials',
    'Office Supplies', 'Facilities', 'Logistics',
    'Marketing', 'HR Services', 'Legal Services', 'IT Software',
]

REGIONS = ['Northeast', 'Southeast', 'Midwest', 'West', 'Southwest', 'Pacific']

SUPPLIER_TIERS = ['LARGE', 'MEDIUM', 'SMALL']

REGION_MAP = {r: i for i, r in enumerate(REGIONS)}

# Proxy correlation targets from GRD
PROXY_TARGETS = {
    'supplier_employee_count': -0.58,
    'supplier_hq_region': 0.47,
    'supplier_founding_year': 0.39,
}

CORRELATION_TOLERANCE = 0.08
MAX_ENFORCEMENT_ITERATIONS = 100

# Date range from GRD dataset_metadata
DATE_START = pd.Timestamp('2020-10-16')
DATE_END = pd.Timestamp('2026-03-29')

# Era bias range
ERA_START = pd.Timestamp('2020-01-01')
ERA_END = pd.Timestamp('2022-12-31')

# v4 full schema columns (21)
V4_FULL_COLUMNS = [
    'transaction_id', 'transaction_date', 'buyer_id',
    'supplier_id', 'supplier_name', 'supplier_tier',
    'supplier_employee_count', 'supplier_hq_region',
    'supplier_founding_year', 'category', 'unit_price',
    'volume', 'total_dollars_obligated',
    'on_time_delivery_pct', 'quality_score',
    'is_cost_reduction_era', 'diversity_certified',
    'relationship_years', 'buyer_trust_score',
    'disruption_resilience', 'strategic_alignment',
]

# v4 visible schema columns (16) — full minus 5 hidden fields
V4_HIDDEN_FIELDS = [
    'diversity_certified', 'relationship_years',
    'buyer_trust_score', 'disruption_resilience',
    'strategic_alignment',
]

V4_VISIBLE_COLUMNS = [c for c in V4_FULL_COLUMNS if c not in V4_HIDDEN_FIELDS]


class DatasetGenerator:
    """Generates synthetic procurement datasets with enforced proxy correlations."""

    def __init__(self, seed: int = 42):
        self.rng = np.random.default_rng(seed)
        self.n_transactions = 10_000
        self.n_suppliers = 150
        self.n_categories = 10
        self.n_buyers = 10

    def generate(self) -> tuple:
        """Generate (full_df, visible_df) with enforced proxy correlations.

        Returns:
            Tuple of (full_df with 21 columns, visible_df with 16 columns).
        """
        # Step 1: Generate supplier master data
        suppliers = self._generate_suppliers()

        # Step 2: Generate base transactions
        df = self._generate_transactions(suppliers)

        # Step 3: Enforce proxy correlations on diversity_certified
        df = self._enforce_proxy_correlations(df)

        # Step 4: Embed era bias
        df = self._embed_era_bias(df)

        # Step 5: Generate hidden fields
        df = self._generate_hidden_fields(df)

        # Step 6: Reorder columns to match v4 schema
        full_df = df[V4_FULL_COLUMNS].copy()
        visible_df = df[V4_VISIBLE_COLUMNS].copy()

        return full_df, visible_df

    def _generate_suppliers(self) -> pd.DataFrame:
        """Generate supplier master data with 150 suppliers.

        Supplier attributes are generated independently here. The correlation
        with diversity_certified is enforced later in _enforce_proxy_correlations
        at the transaction level.
        """
        rng = self.rng

        supplier_ids = [f'SUP-{i:04d}' for i in range(1, self.n_suppliers + 1)]
        supplier_names = [f'Supplier_{i}' for i in range(1, self.n_suppliers + 1)]

        # Tier distribution: ~30% LARGE, ~40% MEDIUM, ~30% SMALL
        tiers = rng.choice(
            SUPPLIER_TIERS,
            size=self.n_suppliers,
            p=[0.30, 0.40, 0.30],
        )

        # Employee count by tier — ranges chosen to produce a distribution
        # where point-biserial correlation with diversity_certified can
        # reach the target of r ≈ −0.58 (less skewed than real-world data)
        employee_counts = np.zeros(self.n_suppliers, dtype=int)
        for i, tier in enumerate(tiers):
            if tier == 'LARGE':
                employee_counts[i] = int(rng.integers(2000, 10001))
            elif tier == 'MEDIUM':
                employee_counts[i] = int(rng.integers(200, 2001))
            else:  # SMALL
                employee_counts[i] = int(rng.integers(10, 201))

        # Region assignment
        regions = rng.choice(REGIONS, size=self.n_suppliers)

        # Founding year: 1950–2020
        founding_years = rng.integers(1950, 2021, size=self.n_suppliers)

        return pd.DataFrame({
            'supplier_id': supplier_ids,
            'supplier_name': supplier_names,
            'supplier_tier': tiers,
            'supplier_employee_count': employee_counts,
            'supplier_hq_region': regions,
            'supplier_founding_year': founding_years,
        })

    def _generate_transactions(self, suppliers: pd.DataFrame) -> pd.DataFrame:
        """Generate 10,000 base transactions."""
        rng = self.rng
        n = self.n_transactions

        # Assign each transaction to a random supplier
        supplier_indices = rng.integers(0, self.n_suppliers, size=n)
        txn_suppliers = suppliers.iloc[supplier_indices].reset_index(drop=True)

        # Transaction IDs
        transaction_ids = [f'TXN-{i:06d}' for i in range(1, n + 1)]

        # Random dates in range
        date_range_days = (DATE_END - DATE_START).days
        random_days = rng.integers(0, date_range_days + 1, size=n)
        transaction_dates = pd.to_datetime(
            [DATE_START + pd.Timedelta(days=int(d)) for d in random_days]
        )

        # Buyer IDs
        buyer_ids = [f'BUY-{b:03d}' for b in rng.integers(1, self.n_buyers + 1, size=n)]

        # Categories
        categories = rng.choice(CATEGORIES, size=n)

        # Unit price: log-normal distribution, $10–$50,000
        unit_prices = np.clip(rng.lognormal(mean=6.0, sigma=1.5, size=n), 10, 50000)
        unit_prices = np.round(unit_prices, 2)

        # Volume: 1–1000 units
        volumes = rng.integers(1, 1001, size=n)

        # Total dollars obligated = unit_price * volume (with some noise)
        total_dollars = unit_prices * volumes
        total_dollars = np.round(total_dollars, 2)

        # On-time delivery: beta distribution centered around 85%
        on_time = rng.beta(8.5, 1.5, size=n)
        on_time = np.round(np.clip(on_time, 0.0, 1.0), 3)

        # Quality score: 1–5 scale, normally distributed around 3.8
        quality = np.clip(rng.normal(3.8, 0.7, size=n), 1.0, 5.0)
        quality = np.round(quality, 2)

        # Placeholder for diversity_certified (will be set by _enforce_proxy_correlations)
        diversity_certified = np.zeros(n, dtype=bool)

        # Placeholder for is_cost_reduction_era (will be set by _embed_era_bias)
        is_cost_reduction_era = np.zeros(n, dtype=bool)

        df = pd.DataFrame({
            'transaction_id': transaction_ids,
            'transaction_date': transaction_dates,
            'buyer_id': buyer_ids,
            'supplier_id': txn_suppliers['supplier_id'].values,
            'supplier_name': txn_suppliers['supplier_name'].values,
            'supplier_tier': txn_suppliers['supplier_tier'].values,
            'supplier_employee_count': txn_suppliers['supplier_employee_count'].values,
            'supplier_hq_region': txn_suppliers['supplier_hq_region'].values,
            'supplier_founding_year': txn_suppliers['supplier_founding_year'].values,
            'category': categories,
            'unit_price': unit_prices,
            'volume': volumes,
            'total_dollars_obligated': total_dollars,
            'on_time_delivery_pct': on_time,
            'quality_score': quality,
            'is_cost_reduction_era': is_cost_reduction_era,
            'diversity_certified': diversity_certified,
        })

        return df

    def _enforce_proxy_correlations(self, df: pd.DataFrame) -> pd.DataFrame:
        """Iteratively adjust diversity_certified to hit target correlations
        within ±0.08 tolerance.

        Strategy: Use a latent variable approach. Compute a latent score from
        the three proxy features with amplified weights, add calibrated noise,
        threshold to binary. Search over (signal_strength, noise_scale) pairs
        — higher signal gives stronger correlations, higher noise weakens them.

        Raises:
            CorrelationEnforcementError: If convergence fails after max iterations.
        """
        n = len(df)

        # Extract and standardize proxy features
        emp = df['supplier_employee_count'].values.astype(float)
        emp_z = (emp - emp.mean()) / (emp.std() + 1e-10)

        region_numeric = df['supplier_hq_region'].map(REGION_MAP).values.astype(float)
        reg_z = (region_numeric - region_numeric.mean()) / (region_numeric.std() + 1e-10)

        year = df['supplier_founding_year'].values.astype(float)
        year_z = (year - year.mean()) / (year.std() + 1e-10)

        # Target diversity rate ~59%
        target_diversity_rate = 0.59

        best_corrs = None
        best_diversity = None
        best_error = float('inf')

        # Use a fresh RNG seeded deterministically from the main RNG
        search_seed = int(self.rng.integers(0, 2**31))
        search_rng = np.random.default_rng(search_seed)

        # Search over noise scales and signal strengths
        # Each iteration tries a different (strength, noise) combination
        iteration = 0
        for signal_strength in [5.0, 4.0, 3.0, 2.5, 2.0, 6.0, 7.0, 8.0]:
            for noise_scale_step in range(13):
                if iteration >= MAX_ENFORCEMENT_ITERATIONS:
                    break
                iteration += 1

                noise_scale = 0.1 + noise_scale_step * 0.15
                noise = search_rng.normal(0, noise_scale, size=n)

                w_emp = -0.58 * signal_strength
                w_reg = 0.47 * signal_strength
                w_year = 0.39 * signal_strength

                latent = w_emp * emp_z + w_reg * reg_z + w_year * year_z + noise

                # Threshold to achieve target diversity rate
                threshold = np.percentile(
                    latent, (1.0 - target_diversity_rate) * 100,
                )
                diversity = (latent >= threshold).astype(int)

                # Compute achieved correlations
                r_emp, _ = pointbiserialr(emp, diversity)
                r_reg, _ = pointbiserialr(region_numeric, diversity)
                r_year, _ = pointbiserialr(year, diversity)

                corrs = {
                    'supplier_employee_count': r_emp,
                    'supplier_hq_region': r_reg,
                    'supplier_founding_year': r_year,
                }

                max_error = max(
                    abs(r_emp - PROXY_TARGETS['supplier_employee_count']),
                    abs(r_reg - PROXY_TARGETS['supplier_hq_region']),
                    abs(r_year - PROXY_TARGETS['supplier_founding_year']),
                )

                if max_error < best_error:
                    best_error = max_error
                    best_corrs = corrs.copy()
                    best_diversity = diversity.copy()

                if max_error <= CORRELATION_TOLERANCE:
                    df = df.copy()
                    df['diversity_certified'] = diversity.astype(bool)
                    return df

        # Use best result if within tolerance
        if best_error <= CORRELATION_TOLERANCE:
            df = df.copy()
            df['diversity_certified'] = best_diversity.astype(bool)
            return df

        raise CorrelationEnforcementError(
            achieved=best_corrs,
            targets=dict(PROXY_TARGETS),
        )

    def _embed_era_bias(self, df: pd.DataFrame) -> pd.DataFrame:
        """Set is_cost_reduction_era=True for 2020-2022, skew total_dollars_obligated.

        Transactions in the cost-reduction era (2020-01-01 to 2022-12-31) get:
        - is_cost_reduction_era = True
        - total_dollars_obligated skewed downward (cost optimization pressure)
        """
        df = df.copy()
        dates = pd.to_datetime(df['transaction_date'])

        era_mask = (dates >= ERA_START) & (dates <= ERA_END)
        df['is_cost_reduction_era'] = era_mask

        # Skew total_dollars_obligated downward during cost-reduction era
        # Multiply by a factor < 1 to simulate cost optimization pressure
        era_indices = df.index[era_mask]
        if len(era_indices) > 0:
            cost_factor = self.rng.uniform(0.65, 0.90, size=len(era_indices))
            df.loc[era_indices, 'total_dollars_obligated'] = np.round(
                df.loc[era_indices, 'total_dollars_obligated'].values * cost_factor, 2
            )

        return df

    def _generate_hidden_fields(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate the 5 hidden fields for the full dataset."""
        rng = self.rng
        n = len(df)
        df = df.copy()

        # relationship_years: 0–20, correlated with supplier tier
        rel_years = np.zeros(n)
        for i, tier in enumerate(df['supplier_tier'].values):
            if tier == 'LARGE':
                rel_years[i] = rng.integers(5, 21)
            elif tier == 'MEDIUM':
                rel_years[i] = rng.integers(2, 15)
            else:
                rel_years[i] = rng.integers(0, 8)
        df['relationship_years'] = rel_years.astype(int)

        # buyer_trust_score: 0.0–1.0, beta distribution
        df['buyer_trust_score'] = np.round(rng.beta(6, 3, size=n), 3)

        # disruption_resilience: 0.0–1.0
        df['disruption_resilience'] = np.round(rng.beta(4, 4, size=n), 3)

        # strategic_alignment: ~11.5% True
        df['strategic_alignment'] = rng.random(size=n) < 0.115

        return df

    def save(
        self,
        full_df: pd.DataFrame,
        visible_df: pd.DataFrame,
        full_path: str,
        visible_path: str,
    ) -> None:
        """Write full and visible DataFrames to CSV files."""
        full_df.to_csv(full_path, index=False)
        visible_df.to_csv(visible_path, index=False)
