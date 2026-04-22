# Requirements Document

## Introduction

The GRT Validation Engine is a computational engine that runs the full GRT-HCI (Goals, Rules, Thresholds with Human Contribution Index) governance analysis and dataset validation pipeline. It extends the existing `grt_engine` package to provide end-to-end validation of procurement datasets against GRD (Governance Rule Document) specifications, produces the 19-metric scoring instrument results, compares Control vs Treatment groups, and generates reports with control-theoretic interpretations (Laplace and Lyapunov). The engine also fixes known bugs in the existing codebase — including a Laplace label swap in threshold calibration, schema mismatches between v3/v4 datasets, and a stub data generator.

## Glossary

- **GRT**: Goals, Rules, Thresholds — the governance framework
- **GRD**: Governance Rule Document — the JSON/markdown specification encoding the six governance principles as computational parameters
- **HCI**: Human Contribution Index — a composite score measuring human governance contribution across frame (H_F), decision (H_D), and residue (H_R) dimensions
- **Validation_Engine**: The computational pipeline that orchestrates proxy detection, threshold calibration, HCI computation, metric scoring, and report generation
- **GRD_Loader**: The component that parses GRD JSON files into GRDConfig objects
- **Schema_Normalizer**: The component that maps v3 and v4 dataset column names to a canonical internal schema
- **Metric_Scorer**: The component that evaluates the 19-metric scoring instrument across three layers (Input, Process, Output)
- **Report_Generator**: The component that produces structured analysis reports with control-theoretic interpretations
- **Dataset_Generator**: The component that generates synthetic procurement datasets with embedded proxy correlations and biases
- **Threshold_Calibrator**: The component that evaluates threshold fire rates against target bands and produces Laplace/Lyapunov interpretations
- **Proxy_Detector**: The component that identifies features correlating with protected attributes above declared thresholds
- **Control_Group**: The experimental group using standard ML with no governance document
- **Treatment_Group**: The experimental group using a complete GRD before building
- **Laplace_Interpretation**: A frequency-domain control-theoretic mapping of threshold miscalibration (over-damped, under-damped, marginally stable)
- **Lyapunov_Interpretation**: A switched-system stability mapping of threshold miscalibration (regime boundary reachability, dwell-time conditions)
- **Fire_Rate**: The fraction of dataset rows that trigger a given threshold
- **Proxy_Pathway**: A feature that correlates with a protected attribute above the declared correlation threshold
- **Disparate_Impact_Ratio**: The ratio of favorable outcomes for the protected group vs the unprotected group (1.0 = parity)

## Requirements

### Requirement 1: GRD JSON Loading and Validation

**User Story:** As a governance analyst, I want to load a GRD JSON file and have it validated against the expected schema, so that I can be confident the governance specification is complete before running analysis.

#### Acceptance Criteria

1. WHEN a valid GRD JSON file path is provided, THE GRD_Loader SHALL parse the file and return a populated GRDConfig object with all six governance principles mapped (frame origin, residue declaration, permanent incompleteness, distributed epistemic authority, temporal honesty, incentive mapping).
2. WHEN a GRD JSON file is missing required top-level keys (goal, rules, thresholds, proxy_exclusion_list, knowledge_triggers), THE GRD_Loader SHALL return a validation error listing each missing key.
3. WHEN a GRD JSON file contains threshold entries missing required fields (threshold_id, name, trigger_condition, target_fire_rate_min, target_fire_rate_max), THE GRD_Loader SHALL return a validation error identifying the incomplete threshold entry.
4. WHEN a GRD JSON file contains proxy_exclusion_list entries, THE GRD_Loader SHALL populate the GRDConfig blocked_features list and proxy_candidates list from the feature names declared in the exclusion list.
5. WHEN a GRD JSON file contains a reviewer_knowledge_roster, THE GRD_Loader SHALL populate the authority routing map so that each threshold ID maps to its declared reviewer knowledge domain and buyer tier.
6. FOR ALL valid GRD JSON files, loading then serializing back to JSON then loading again SHALL produce an equivalent GRDConfig object (round-trip property).

### Requirement 2: Dataset Schema Normalization

**User Story:** As a governance analyst, I want to load both v3 and v4 dataset formats and have them normalized to a canonical schema, so that the engine works regardless of which dataset version is provided.

#### Acceptance Criteria

1. WHEN a v4 dataset CSV is loaded (columns: transaction_id, transaction_date, buyer_id, supplier_id, supplier_name, supplier_tier, supplier_employee_count, supplier_hq_region, supplier_founding_year, category, unit_price, volume, total_dollars_obligated, on_time_delivery_pct, quality_score, is_cost_reduction_era, and optionally diversity_certified, relationship_years, buyer_trust_score, disruption_resilience, strategic_alignment), THE Schema_Normalizer SHALL return a DataFrame with canonical column names unchanged.
2. WHEN a v3 dataset CSV is loaded (columns: employee_count, recipient_state_code, founding_year, action_date), THE Schema_Normalizer SHALL map employee_count to supplier_employee_count, recipient_state_code to supplier_hq_region, founding_year to supplier_founding_year, and action_date to transaction_date.
3. WHEN a dataset CSV is missing columns required by the GRD proxy_exclusion_list, THE Schema_Normalizer SHALL return an error listing each missing column after normalization.
4. WHEN a visible dataset (no hidden fields) and a full dataset (with hidden fields) are both loaded, THE Schema_Normalizer SHALL verify that the visible dataset row count matches the full dataset row count.
5. FOR ALL datasets that successfully normalize, THE Schema_Normalizer SHALL preserve the original row count and all non-renamed column values exactly.

### Requirement 3: Proxy Detection Pipeline

**User Story:** As a governance analyst, I want the engine to detect proxy pathways between visible features and protected attributes, so that I can verify the GRD's corruption surface declarations.

#### Acceptance Criteria

1. WHEN proxy detection is run on a full dataset with declared proxy candidates and protected attributes, THE Proxy_Detector SHALL compute Pearson correlation and p-value for each candidate-attribute pair.
2. WHEN a feature-attribute pair has absolute correlation at or above the configured proxy_correlation_threshold and p-value below 0.05, THE Proxy_Detector SHALL classify the pair as a proxy pathway.
3. WHEN a detected proxy feature is listed in the GRD blocked_features, THE Proxy_Detector SHALL mark the proxy as blocked and include the block status in the ProxyReport.
4. THE Proxy_Detector SHALL compute the boundary enforcement rate (M6) as the count of blocked proxies divided by the count of detected proxies, returning 1.0 when no proxies are detected.
5. WHEN proxy detection completes, THE Proxy_Detector SHALL produce a ProxyReport containing: total candidates scanned, proxies found, proxies blocked, proxy influence percentage, boundary enforcement rate, and per-pair correlation details.
6. WHEN fewer than 30 valid (non-NaN) paired observations exist for a feature-attribute pair, THE Proxy_Detector SHALL skip that pair and exclude the pair from the ProxyReport results.

### Requirement 4: Threshold Calibration with Correct Control-Theoretic Labels

**User Story:** As a governance analyst, I want threshold calibration to produce correct Laplace-domain and Lyapunov switched-system interpretations, so that miscalibrations are diagnosed with the right control-theoretic failure mode.

#### Acceptance Criteria

1. WHEN a threshold fire rate falls below the target band lower bound, THE Threshold_Calibrator SHALL produce a Laplace_Interpretation describing over-damped response (gain too low, sluggish governance response — the threshold is set too high so it under-fires, matching T1/T2 in THRESHOLDS.md and §4.4 of the paper).
2. WHEN a threshold fire rate exceeds the target band upper bound but is below 0.80, THE Threshold_Calibrator SHALL produce a Laplace_Interpretation describing marginally stable response (gain too high, risk of oscillation — the threshold is set too low so it over-fires, matching T4 in THRESHOLDS.md and §4.4 of the paper).
3. WHEN a threshold fire rate is within the target band, THE Threshold_Calibrator SHALL produce a Laplace_Interpretation of "Gain correctly tuned" and a status of "CALIBRATED".
4. WHEN a threshold fire rate exceeds 0.80, THE Threshold_Calibrator SHALL produce a Lyapunov_Interpretation describing a degenerate switched system where the regime boundary is unreachable from below.
5. WHEN a threshold fire rate is 0.0, THE Threshold_Calibrator SHALL produce a Lyapunov_Interpretation describing a degenerate switched system where the regime boundary is unreachable from the current state space.
6. WHEN threshold calibration completes, THE Threshold_Calibrator SHALL produce a CalibrationReport with counts of calibrated, miscalibrated, and pending thresholds, plus per-threshold fire rate, status, Laplace_Interpretation, Lyapunov_Interpretation, and recalibration action.
7. IF a threshold has no registered threshold function, THEN THE Threshold_Calibrator SHALL mark the threshold as PENDING and set the control interpretation to "Cannot evaluate — no threshold function provided".

### Requirement 5: HCI Computation

**User Story:** As a governance analyst, I want to compute the Human Contribution Index for both Control and Treatment configurations, so that I can quantify the governance contribution difference.

#### Acceptance Criteria

1. WHEN HCI is computed with frame authorship, documentation, and challenge parameters, THE HCI_Calculator SHALL compute H_F as the weighted sum using the configured hf_weights (default equal thirds).
2. WHEN HCI is computed with a decision position string, THE HCI_Calculator SHALL look up the position value from the configured hd_positions map and use the value as H_D.
3. WHEN HCI is computed with residue surfacing, authorization, and timeliness parameters, THE HCI_Calculator SHALL compute H_R as the weighted sum using the configured hr_weights (default equal thirds).
4. THE HCI_Calculator SHALL compute three aggregations: geometric mean (cube root of H_F × H_D × H_R when all positive, else 0.0), arithmetic mean ((H_F + H_D + H_R) / 3), and minimum (min of H_F, H_D, H_R).
5. WHEN comparing Control and Treatment HCI results, THE HCI_Calculator SHALL produce a formatted comparison table showing H_F, H_D, H_R, and primary HCI for each system.

### Requirement 6: 19-Metric Scoring Instrument

**User Story:** As a governance analyst, I want the engine to score all 19 metrics across three layers (Input, Process, Output), so that I can evaluate governance effectiveness with the full instrument.

#### Acceptance Criteria

1. THE Metric_Scorer SHALL score Layer 1 metrics (M1 through M5) using the GRD specification: M1 Goal Definition Maturity (0–12), M2 Rule Specification (0–5 domains), M3 Deployment-Level Decision (1–5), M4 Proxy Detection (found/embedded count), M5 Frame Mapping (0–10).
2. THE Metric_Scorer SHALL score Layer 2 metrics (M6 through M9) using pipeline results: M6 Frame-Mismatch Flagging (pass/fail), M7 Threshold Fire Patterns (pass/fail per threshold), M8 Boundary Enforcement (0–100%), M9 Authority Routing (pass/fail).
3. THE Metric_Scorer SHALL mark Layer 2 metrics M10 through M13 as PENDING when no post-deployment data is available.
4. THE Metric_Scorer SHALL score Layer 3 metrics (M14 through M19) using model output analysis: M14 Bias Reduction (Disparate_Impact_Ratio), M15 Proxy Influence (percentage), M16 Resilience under Disruption (pass/fail), M17 Strategic-Alignment Preservation (pass/fail), M18 Frame Transparency (percentage), M19 Auditability (percentage).
5. WHEN scoring each metric, THE Metric_Scorer SHALL produce a Control value, a Treatment value, a verdict (PASS, FAIL, PENDING, or INCONCLUSIVE), and a one-line finding.
6. THE Metric_Scorer SHALL map metrics to claims (C1 through C5) using the declared metric-to-claim mapping and produce a claim verdict (CONFIRMED, PARTIALLY CONFIRMED, INCONCLUSIVE, or PENDING) based on the primary metrics for each claim.

### Requirement 7: Control vs Treatment Comparison Pipeline

**User Story:** As a governance analyst, I want to run the full pipeline comparing a Control group (no GRD) against a Treatment group (with GRD), so that I can evaluate all five experimental claims.

#### Acceptance Criteria

1. WHEN a full analysis is run, THE Validation_Engine SHALL execute stages in order: (1) dataset loading and schema normalization, (2) proxy detection, (3) threshold calibration, (4) HCI computation for Control and Treatment, (5) 19-metric scoring, (6) claim verdict evaluation.
2. WHEN the Control configuration is evaluated, THE Validation_Engine SHALL use default parameters: no blocked features, no declared thresholds, no GRD frame, deployment level 1.
3. WHEN the Treatment configuration is evaluated, THE Validation_Engine SHALL use the loaded GRD parameters: blocked features from proxy_exclusion_list, thresholds from knowledge_triggers, full frame specification, declared deployment level.
4. WHEN all stages complete, THE Validation_Engine SHALL produce an AnalysisReport containing proxy report, calibration report, HCI comparison, all 19 metric scores, and five claim verdicts.
5. IF any stage fails with a data error, THEN THE Validation_Engine SHALL halt the pipeline and return a structured error identifying the failed stage and the cause.

### Requirement 8: Dataset Integrity Verification

**User Story:** As a governance analyst, I want to verify dataset integrity against the GRD specification before running analysis, so that I can catch data issues early.

#### Acceptance Criteria

1. WHEN dataset verification is run, THE Validation_Engine SHALL check that the row count is within the expected range (9,500 to 10,500 for the procurement dataset).
2. WHEN dataset verification is run against a GRD, THE Validation_Engine SHALL verify that all columns referenced in the GRD proxy_exclusion_list exist in the normalized dataset.
3. WHEN dataset verification is run, THE Validation_Engine SHALL compute proxy correlations for each declared proxy pathway and compare against the GRD-declared target correlations with a configurable tolerance.
4. WHEN dataset verification is run, THE Validation_Engine SHALL verify that all reason_weights keys declared in the GRD are present.
5. WHEN a proxy correlation deviates from the GRD target by more than the configured tolerance, THE Validation_Engine SHALL report the deviation as a warning (not a failure) with the observed and target values.
6. WHEN the T3 threshold fire rate (total_dollars_obligated > 500000) is outside the GRD-declared target band (15–22%), THE Validation_Engine SHALL report the actual fire rate and flag the discrepancy.

### Requirement 9: Report Generation with Control-Theoretic Interpretations

**User Story:** As a governance analyst, I want structured reports in both human-readable text and machine-readable JSON, so that I can review results and feed them into downstream tools.

#### Acceptance Criteria

1. WHEN a text report is generated, THE Report_Generator SHALL include sections for: proxy detection summary, threshold calibration with Laplace and Lyapunov interpretations per threshold, HCI comparison table, 19-metric scorecard with Control/Treatment/Verdict columns, and claim verdicts with supporting metrics.
2. WHEN a JSON report is generated, THE Report_Generator SHALL include all numeric values, verdicts, interpretations, and metadata (GRD name, timestamp, dataset row count) in a structured format.
3. FOR ALL generated JSON reports, parsing the JSON then re-serializing SHALL produce byte-identical output (round-trip property).
4. WHEN a threshold is miscalibrated, THE Report_Generator SHALL include the specific recalibration action (e.g., "Reduce threshold sensitivity to bring fire rate into X%–Y% band").
5. WHEN claim verdicts are generated, THE Report_Generator SHALL list the supporting primary and secondary metrics for each claim alongside the verdict.

### Requirement 10: Laplace Label Swap Bug Fix

**User Story:** As a developer, I want the Laplace-domain labels in threshold_calibrator.py to be corrected so that the labels match the paper (§4.4) and THRESHOLDS.md: under-firing thresholds are labeled as over-damped (sluggish, gain too low) and over-firing thresholds are labeled as marginally stable (oscillation risk, gain too high).

#### Acceptance Criteria

1. WHEN a threshold fire rate is below the target band lower bound and above 0.0, THE Threshold_Calibrator SHALL include "over-damped" in the Laplace_Interpretation string, because under-firing corresponds to gain too low — the governance regime does not react quickly enough (matching T1/T2 in THRESHOLDS.md: "Over-damped response. Governance does not react quickly enough" / "Gain too low").
2. WHEN a threshold fire rate exceeds the target band upper bound but is below 0.80, THE Threshold_Calibrator SHALL include "marginally stable" in the Laplace_Interpretation string, because over-firing corresponds to gain too high — the threshold fires on noise, producing sustained oscillation (matching T4 in THRESHOLDS.md: "Marginally stable. The threshold fires on the median... producing sustained low-amplitude oscillation").
3. WHEN a threshold fire rate is 0.0, THE Threshold_Calibrator SHALL include "gain starvation" in the Laplace_Interpretation string (controller never activates — extreme over-damped case).
4. WHEN a threshold fire rate exceeds 0.80, THE Threshold_Calibrator SHALL include "gain saturation" in the Laplace_Interpretation string (controller always on — degenerate case, no discrimination).

### Requirement 11: Unused Import Cleanup

**User Story:** As a developer, I want unused imports removed from the engine modules, so that the codebase is clean and passes linting.

#### Acceptance Criteria

1. THE Threshold_Calibrator module SHALL not import numpy when numpy is not used in the module body.
2. THE Validation_Engine codebase SHALL contain no unused imports across all engine modules.

### Requirement 12: Synthetic Dataset Generation

**User Story:** As a governance analyst, I want a working dataset generator that produces procurement datasets with the declared proxy correlations and embedded biases, so that experiments are reproducible.

#### Acceptance Criteria

1. WHEN the Dataset_Generator is run with seed=42, THE Dataset_Generator SHALL produce a full dataset CSV with 10,000 rows and 21 columns matching the v4 schema (transaction_id, transaction_date, buyer_id, supplier_id, supplier_name, supplier_tier, supplier_employee_count, supplier_hq_region, supplier_founding_year, category, unit_price, volume, total_dollars_obligated, on_time_delivery_pct, quality_score, is_cost_reduction_era, diversity_certified, relationship_years, buyer_trust_score, disruption_resilience, strategic_alignment).
2. WHEN the Dataset_Generator is run with seed=42, THE Dataset_Generator SHALL produce a visible dataset CSV with 10,000 rows and 16 columns (the full dataset minus the five hidden fields: diversity_certified, relationship_years, buyer_trust_score, disruption_resilience, strategic_alignment).
3. WHEN the Dataset_Generator is run, THE Dataset_Generator SHALL enforce proxy correlations within a tolerance of ±0.08 of the GRD-declared targets: supplier_employee_count ↔ diversity_certified target r = −0.58, supplier_hq_region ↔ diversity_certified target r = +0.47, supplier_founding_year ↔ diversity_certified target r = +0.39.
4. WHEN the Dataset_Generator is run, THE Dataset_Generator SHALL embed the cost-reduction era bias: transactions dated 2020-01-01 through 2022-12-31 SHALL have is_cost_reduction_era = true and a measurable cost-optimization skew in total_dollars_obligated.
5. WHEN the Dataset_Generator is run with the same seed, THE Dataset_Generator SHALL produce identical output files (deterministic generation).
