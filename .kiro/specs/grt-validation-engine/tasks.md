# Implementation Plan: GRT Validation Engine

## Overview

Build the GRT Validation Engine by extending the existing `grt_engine` Python package with six new modules and fixes to two existing modules. Tasks are ordered: bug fixes and config extensions first, then new modules in dependency order (loader → normalizer → scorer → generator → report), then engine orchestrator wiring, then integration tests. All code lives in `grt-hci/grt_engine/` with tests in `grt-hci/tests/`.

## Tasks

- [x] 1. Fix threshold_calibrator.py bugs and extend config.py
  - [x] 1.1 Fix Laplace label swap in threshold_calibrator.py
    - In `_laplace_interpretation()`, correct the labels: under-firing (fire_rate < lower_bound, > 0) → "Over-damped" (gain too low, sluggish); over-firing (fire_rate > upper_bound, < 0.80) → "Marginally stable" (gain too high, oscillation risk); fire_rate == 0 → "Gain starvation"; fire_rate > 0.80 → "Gain saturation"
    - Update the `§4.4` references to remove the incorrect "under-damped" / "over-damped" suffixes
    - Remove the unused `import numpy as np` from the top of the file
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 11.1_

  - [x] 1.2 Fix ThresholdSpec.is_calibrated() return values in config.py
    - Change return values from `'UNDER (gain starvation)'` / `'OVER (gain saturation)'` to plain `'UNDER'` / `'OVER'` so downstream status checks work consistently
    - _Requirements: 4.3, 4.6_

  - [x] 1.3 Extend GRDConfig in config.py with new fields
    - Add `authority_routing: Dict[str, Dict[str, str]]` (maps threshold_id → knowledge/buyer_tier)
    - Add `deployment_level: int = 1`
    - Add `reason_weights: Dict[str, float]`
    - Add `era_bias_config: Dict[str, Any]`
    - Add `dataset_metadata: Dict[str, Any]`
    - Add necessary imports (`Any` from typing)
    - _Requirements: 1.5, 7.2, 7.3_

  - [ ]* 1.4 Write property tests for Laplace/Lyapunov label correctness
    - **Property 9: Laplace labels match paper — under-firing is over-damped, over-firing is marginally stable**
    - **Validates: Requirements 4.1, 4.2, 4.3, 10.1, 10.2, 10.3, 10.4**
    - Create `tests/test_threshold_calibrator.py` using Hypothesis
    - Generate random ThresholdSpec (target bands) and fire rates, assert correct label substrings

  - [ ]* 1.5 Write property tests for Lyapunov degenerate cases and calibration report counts
    - **Property 10: Lyapunov degenerate cases are correctly identified**
    - **Validates: Requirements 4.4, 4.5**
    - **Property 11: Calibration report counts are consistent**
    - **Validates: Requirements 4.6**
    - Add to `tests/test_threshold_calibrator.py`

- [x] 2. Checkpoint — Verify bug fixes
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Implement GRD Loader (grt_engine/grd_loader.py)
  - [x] 3.1 Create grd_loader.py with GRDLoader class and GRDValidationError
    - Implement `GRDLoader.load(path)` — parse GRD JSON, validate required top-level keys (`goal`, `rules`, `thresholds`, `proxy_exclusion_list`, `knowledge_triggers`) and threshold fields (`threshold_id`, `name`, `trigger_condition`, `target_fire_rate_min`, `target_fire_rate_max`)
    - Implement `GRDLoader.validate(raw)` — return list of validation error strings
    - Implement `GRDLoader.to_json(config)` — serialize GRDConfig back to JSON-compatible dict
    - Map `knowledge_triggers` → `thresholds` (list of ThresholdSpec), `proxy_exclusion_list` → `blocked_features`/`proxy_candidates`, `reviewer_knowledge_roster` → `authority_routing`, `reason_weights`/`deployment_decision`/`data_vintage_config`/`residue_domains` → corresponding GRDConfig fields
    - Note: The actual `grd_procurement_v1.json` uses different top-level keys than the required validation keys — the loader must map the actual GRD structure (which has `residue_domains`, `knowledge_triggers`, etc. at top level) to the logical validation categories. Treat `knowledge_triggers` as the `thresholds` key, `proxy_exclusion_list` as itself, and derive `goal`/`rules` from the presence of `deployment_decision`/`reason_weights`/`non_goal_guardrails`/`epistemic_territory_rules`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [ ]* 3.2 Write property tests for GRD loader
    - **Property 1: GRD round-trip serialization**
    - **Validates: Requirements 1.6**
    - **Property 2: GRD validation reports exactly the missing keys**
    - **Validates: Requirements 1.2, 1.3**
    - **Property 3: GRD field mapping preserves declared features and routing**
    - **Validates: Requirements 1.4, 1.5**
    - Create `tests/test_grd_loader.py` using Hypothesis

- [x] 4. Implement Schema Normalizer (grt_engine/schema_normalizer.py)
  - [x] 4.1 Create schema_normalizer.py with SchemaNormalizer class and SchemaError
    - Implement `detect_version(df)` — return `'v3'` or `'v4'` based on column names
    - Implement `normalize(df)` — detect version, rename v3 columns to canonical v4 names, validate required columns present after normalization
    - Implement `validate_against_grd(df, config)` — check all GRD-referenced columns exist
    - Implement `verify_row_counts(visible_df, full_df)` — verify matching row counts
    - Define `V3_TO_CANONICAL` mapping dict, `V4_REQUIRED_VISIBLE` list, `V4_HIDDEN_FIELDS` list
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [ ]* 4.2 Write property tests for schema normalizer
    - **Property 4: Schema normalization preserves row count and values**
    - **Validates: Requirements 2.1, 2.5**
    - **Property 5: v3 schema columns are correctly renamed**
    - **Validates: Requirements 2.2**
    - **Property 6: Schema validation reports exactly the missing GRD-referenced columns**
    - **Validates: Requirements 2.3**
    - Create `tests/test_schema_normalizer.py` using Hypothesis

- [x] 5. Checkpoint — Verify loader and normalizer
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement Metric Scorer (grt_engine/metric_scorer.py)
  - [x] 6.1 Create metric_scorer.py with MetricScore, ClaimVerdict, MetricScorecard dataclasses and MetricScorer class
    - Define `METRIC_TO_CLAIM_MAP` mapping C1–C5 to primary/secondary metrics per METRICS.md
    - Implement `score_all()` — score Layer 1 (M1–M5) from GRD spec, Layer 2 (M6–M9) from pipeline results, mark M10–M13 as PENDING, score Layer 3 (M14–M19) from control/treatment params
    - Implement `evaluate_claims()` — produce ClaimVerdict for each claim based on primary metric verdicts
    - Each MetricScore has: metric_id, name, layer, control_value, treatment_value, verdict (PASS/FAIL/PENDING/INCONCLUSIVE), finding
    - Each ClaimVerdict has: claim_id, description, verdict (CONFIRMED/PARTIALLY_CONFIRMED/INCONCLUSIVE/PENDING), primary_metrics, secondary_metrics, rationale
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [ ]* 6.2 Write property tests for metric scorer
    - **Property 14: Metric scores have all required fields**
    - **Validates: Requirements 6.5**
    - **Property 15: Claim verdicts follow the metric-to-claim mapping**
    - **Validates: Requirements 6.6**
    - Create `tests/test_metric_scorer.py` using Hypothesis

- [x] 7. Implement Dataset Generator (grt_engine/dataset_generator.py)
  - [x] 7.1 Create dataset_generator.py with DatasetGenerator class
    - Implement `generate()` — produce (full_df, visible_df) tuple with 10,000 rows
    - Full dataset: 21 columns matching v4 schema; visible dataset: 16 columns (full minus 5 hidden fields)
    - Implement `_enforce_proxy_correlations(df)` — iteratively adjust diversity_certified to hit target correlations within ±0.08 (employee_count ↔ diversity r=−0.58, hq_region ↔ diversity r=+0.47, founding_year ↔ diversity r=+0.39)
    - Implement `_embed_era_bias(df)` — set is_cost_reduction_era=True for 2020–2022 transactions, skew total_dollars_obligated
    - Implement `save(full_df, visible_df, full_path, visible_path)` — write CSVs
    - Use `np.random.default_rng(seed)` for deterministic generation
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5_

  - [ ]* 7.2 Write property tests for dataset generator
    - **Property 18: Dataset generator is deterministic**
    - **Validates: Requirements 12.5**
    - **Property 19: Dataset generator enforces proxy correlations within tolerance**
    - **Validates: Requirements 12.3**
    - Create `tests/test_dataset_generator.py` using Hypothesis

- [x] 8. Implement Report Generator (grt_engine/report_generator.py)
  - [x] 8.1 Create report_generator.py with ReportGenerator class
    - Implement `generate_text(report, scorecard)` — human-readable text with sections: proxy detection summary, threshold calibration with Laplace/Lyapunov interpretations, HCI comparison table, 19-metric scorecard (Control/Treatment/Verdict), claim verdicts with supporting metrics
    - Implement `generate_json(report, scorecard)` — machine-readable JSON with all numeric values, verdicts, interpretations, metadata (GRD name, timestamp, row count)
    - Implement `serialize_json(report_dict)` — `json.dumps(report_dict, sort_keys=True, indent=2)` for round-trip stability
    - Include non-empty recalibration action for each miscalibrated threshold
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [ ]* 8.2 Write property tests for report generator
    - **Property 16: JSON report round-trip produces byte-identical output**
    - **Validates: Requirements 9.3**
    - **Property 17: Miscalibrated thresholds have non-empty recalibration actions in reports**
    - **Validates: Requirements 9.4**
    - Create `tests/test_report_generator.py` using Hypothesis

- [x] 9. Checkpoint — Verify all new modules
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Wire engine orchestrator and dataset verification
  - [x] 10.1 Extend GRTEngine in engine.py with new pipeline methods
    - Add `load_grd(path)` — load GRD JSON via GRDLoader, set self.config
    - Add `normalize_schema()` — normalize loaded dataset via SchemaNormalizer
    - Add `verify_dataset(tolerance=0.08)` — run dataset integrity checks (row count 9500–10500, GRD-referenced columns exist, proxy correlations within tolerance, reason_weights keys present, T3 fire rate check)
    - Add `score_metrics(control_params, treatment_params)` — score all 19 metrics and evaluate claims via MetricScorer
    - Add `generate_report(format='text')` — generate report via ReportGenerator
    - Add `PipelineError` exception class for stage failures
    - Update `run_full_analysis()` to include schema normalization, metric scoring, and report generation stages
    - Update imports in `__init__.py` to export new modules
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

  - [ ]* 10.2 Write property tests for dataset verification
    - **Property 20: Dataset verification reports correlation deviations as warnings**
    - **Validates: Requirements 8.5**
    - **Property 21: Row count verification accepts valid range and rejects outside**
    - **Validates: Requirements 8.1**
    - Create `tests/test_dataset_verification.py` using Hypothesis

  - [ ]* 10.3 Write property tests for proxy detection and HCI
    - **Property 7: Proxy classification matches correlation threshold**
    - **Validates: Requirements 3.2, 3.3**
    - **Property 8: Boundary enforcement rate is correctly computed**
    - **Validates: Requirements 3.4**
    - Create `tests/test_proxy_detector.py` using Hypothesis
    - **Property 12: HCI sub-indices are weighted sums of their components**
    - **Validates: Requirements 5.1, 5.3**
    - **Property 13: HCI geometric mean is zero when any sub-index is zero**
    - **Validates: Requirements 5.4**
    - Create `tests/test_hci.py` using Hypothesis

- [x] 11. Checkpoint — Verify orchestrator wiring
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. Integration tests and unused import cleanup
  - [x] 12.1 Write integration tests for the full pipeline
    - Create `tests/test_pipeline_integration.py`
    - Test: generate dataset → load GRD → normalize schema → run full analysis → generate text and JSON reports
    - Verify report contains all sections and correct threshold interpretations
    - Verify Control config uses defaults (no blocked features, no thresholds, deployment level 1)
    - Verify Treatment config uses GRD parameters
    - Verify pipeline halts on data error with PipelineError
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [x] 12.2 Verify no unused imports across all engine modules
    - Scan all files in `grt_engine/` for unused imports
    - Confirm the numpy import was removed from threshold_calibrator.py in task 1.1
    - _Requirements: 11.1, 11.2_

  - [x] 12.3 Update requirements.txt with hypothesis dependency
    - Add `hypothesis>=6.82.0` to the development dependencies section
    - _Requirements: (testing infrastructure)_

- [x] 13. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation after each logical group
- Property tests use Hypothesis and validate the 21 correctness properties from the design document
- The implementation language is Python throughout (matching the existing codebase and design)
- All new modules go in `grt-hci/grt_engine/`, all tests go in `grt-hci/tests/`
