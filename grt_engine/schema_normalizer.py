"""
Schema Normalizer — maps v3 and v4 dataset column schemas to a canonical internal schema.

Pure functions: DataFrame in → DataFrame out. Detects schema version, renames
v3 columns to canonical v4 names, validates required columns, and checks
GRD-referenced columns exist.
"""

import pandas as pd
from typing import List

from grt_engine.config import GRDConfig


# ── Column mappings ──

V3_TO_CANONICAL = {
    'employee_count': 'supplier_employee_count',
    'recipient_state_code': 'supplier_hq_region',
    'founding_year': 'supplier_founding_year',
    'action_date': 'transaction_date',
}

V4_REQUIRED_VISIBLE = [
    'transaction_id', 'transaction_date', 'buyer_id',
    'supplier_id', 'supplier_name', 'supplier_tier',
    'supplier_employee_count', 'supplier_hq_region',
    'supplier_founding_year', 'category', 'unit_price',
    'volume', 'total_dollars_obligated',
    'on_time_delivery_pct', 'quality_score',
    'is_cost_reduction_era',
]

V4_HIDDEN_FIELDS = [
    'diversity_certified', 'relationship_years',
    'buyer_trust_score', 'disruption_resilience',
    'strategic_alignment',
]


class SchemaError(Exception):
    """Raised when schema normalization or validation fails."""

    def __init__(self, missing_columns: List[str]):
        self.missing_columns = missing_columns
        super().__init__(f"Missing columns after normalization: {missing_columns}")


class SchemaNormalizer:
    """Detects dataset schema version and normalizes to canonical v4 column names."""

    @staticmethod
    def detect_version(df: pd.DataFrame) -> str:
        """Return 'v3' or 'v4' based on column names present.

        v3 is identified by the presence of any v3-specific column name
        (employee_count, recipient_state_code, founding_year, action_date).
        v4 is identified by the presence of canonical column names.
        Raises SchemaError if neither version is detected.
        """
        cols = set(df.columns)
        v3_keys = set(V3_TO_CANONICAL.keys())

        if cols & v3_keys:
            return 'v3'

        v4_required = set(V4_REQUIRED_VISIBLE)
        if v4_required.issubset(cols):
            return 'v4'

        # Check if it's a partial v4 — still treat as v4 if it has canonical
        # names for the columns that would be renamed in v3
        canonical_renamed = set(V3_TO_CANONICAL.values())
        if cols & canonical_renamed:
            return 'v4'

        raise SchemaError(
            missing_columns=sorted(v4_required - cols),
        )

    @staticmethod
    def normalize(df: pd.DataFrame) -> pd.DataFrame:
        """Detect schema version, rename v3 columns to canonical names, validate.

        Returns a new DataFrame with canonical column names.
        Raises SchemaError if required columns are missing after normalization.
        """
        version = SchemaNormalizer.detect_version(df)

        if version == 'v3':
            # Rename only the columns that exist in the DataFrame
            rename_map = {
                k: v for k, v in V3_TO_CANONICAL.items() if k in df.columns
            }
            result = df.rename(columns=rename_map)
        else:
            result = df.copy()

        # Validate that required visible columns are present
        result_cols = set(result.columns)
        required = set(V4_REQUIRED_VISIBLE)
        missing = sorted(required - result_cols)

        if missing:
            raise SchemaError(missing_columns=missing)

        return result

    @staticmethod
    def validate_against_grd(df: pd.DataFrame, config: GRDConfig) -> List[str]:
        """Check that all columns referenced in the GRD exist in the DataFrame.

        Validates that every column in config.blocked_features and
        config.proxy_candidates is present in df.columns.

        Returns a list of error strings (empty if all columns exist).
        """
        errors: List[str] = []
        df_cols = set(df.columns)

        for col in config.blocked_features:
            if col not in df_cols:
                errors.append(
                    f"GRD blocked_feature '{col}' not found in dataset columns"
                )

        for col in config.proxy_candidates:
            if col not in df_cols:
                errors.append(
                    f"GRD proxy_candidate '{col}' not found in dataset columns"
                )

        return errors

    @staticmethod
    def verify_row_counts(visible_df: pd.DataFrame, full_df: pd.DataFrame) -> bool:
        """Verify that visible and full datasets have matching row counts."""
        return len(visible_df) == len(full_df)
