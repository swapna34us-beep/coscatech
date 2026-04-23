# Implementation Plan: Live Recommendation Tester

## Overview

Build a self-contained HTML page (`grt-hci/grt_live_tester.html`) that runs a dual recommendation engine (Control vs Treatment) in the browser. A Python aggregation script generates the embedded dataset from the full CSV. The page implements 6 JS modules (DataLoader, RecommendationEngine, ThresholdEvaluator, HCICalculator, SessionManager, UI Layer) with styling matching `grt_dashboard.html`.

## Tasks

- [x] 1. Generate embedded supplier-profile dataset
  - [x] 1.1 Create Python aggregation script `grt-hci/scripts/aggregate_profiles.py`
    - Read `procurement_data_full_v4.csv` and group rows by `(supplier_id, category)`
    - Compute averages for numeric fields: unit_price, volume, total_dollars_obligated, on_time_delivery_pct, quality_score
    - Compute `is_cost_reduction_era_pct` as the mean of the boolean column per group
    - Compute `transaction_count` as the row count per group
    - Compute `last_transaction_date` as the max transaction_date per group
    - For boolean hidden fields (diversity_certified, strategic_alignment), take the mode
    - For numeric hidden fields (relationship_years, buyer_trust_score, disruption_resilience), compute averages
    - Compute `category_spend_share` as supplier's total spend in category / total category spend
    - Carry forward: supplier_name, supplier_tier, supplier_employee_count, supplier_hq_region, supplier_founding_year
    - Output JSON array to stdout (for embedding) and optionally to a file
    - _Requirements: 1.1_

  - [x] 1.2 Run the aggregation script and verify output
    - Execute `aggregate_profiles.py` against `procurement_data_full_v4.csv`
    - Verify output contains ~500–800 supplier-category profiles from 150 unique suppliers across 10 categories
    - Verify all 21 fields are present in each profile object
    - _Requirements: 1.1, 1.5_

- [x] 2. Create HTML skeleton with CSS
  - [x] 2.1 Create `grt-hci/grt_live_tester.html` with page structure and styles
    - Create the HTML file with `<!DOCTYPE html>`, meta tags, and title "GRT-HCI Live Recommendation Tester"
    - Copy the CSS class system from `grt_dashboard.html` (color palette #1B3A5C / #2E6DA4 / #1F7A4D / #C55A11, card layout, compact typography, `.top`, `.w`, `.card`, `.ch`, `.cb`, `.rb`, `.bg`, `.phase` classes)
    - Add placeholder `<div>` containers for all 13 UI panels: Data Summary, Procurement Need, Scoring Weights, Reason Weights, Threshold Tuning, Side-by-Side, Difference Summary, Threshold Fires, Hidden Fields, HCI Comparison, Override Panel, GRD Summary, Session Summary
    - Add the sticky top bar with title and "Run Recommendations" button
    - Embed the GRD_CONFIG JavaScript object from the design (proxy_exclusions, reason_weights, non_goal_guardrails, thresholds, residue_domains, deployment, category_risk_weights)
    - _Requirements: 10.1, 10.4_

- [x] 3. Implement DataLoader module
  - [x] 3.1 Embed the aggregated JSON dataset and implement DataLoader
    - Paste the JSON output from step 1.2 into a `<script>` tag as `const EMBEDDED_DATA = [...]`
    - Implement `DataLoader.loadEmbedded()` to return the embedded profiles
    - Implement `DataLoader.validateColumns(headers)` to check for the 16 required visible columns and return missing column names
    - Implement `DataLoader.parseCSV(csvText)` to parse uploaded CSV, group by (supplier_id, category), compute aggregated profiles, and return `{ profiles, errors }`
    - Implement `DataLoader.getProfiles(category, minBudget, maxBudget, tiers)` to filter profiles by category, budget range on avg_total_dollars_obligated, and supplier tier
    - Implement `DataLoader.getSummary()` to return transaction count, unique supplier count, and unique category count
    - Handle edge cases: malformed CSV, empty CSV, non-numeric values (skip rows with warning)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.3, 2.4, 2.5_

  - [ ]* 3.2 Write property test for CSV column validation
    - **Property 1: CSV Column Validation Returns Exact Missing Set**
    - **Validates: Requirements 1.3**

  - [ ]* 3.3 Write property test for failed upload preserving state
    - **Property 2: Failed Upload Preserves Dataset State**
    - **Validates: Requirements 1.4**

  - [ ]* 3.4 Write property test for dataset summary accuracy
    - **Property 3: Dataset Summary Accuracy**
    - **Validates: Requirements 1.5**

  - [ ]* 3.5 Write property test for budget range filtering
    - **Property 4: Budget Range Filtering**
    - **Validates: Requirements 2.4, 2.5**

- [x] 4. Implement RecommendationEngine module
  - [x] 4.1 Implement scoring and ranking logic
    - Implement `normalize(values)` using min-max normalization to [0, 1]; handle single-value and all-identical edge cases (return 0.5)
    - Implement `scoreControl(profiles, weights)`: normalize 5 scoring features + 3 proxy features (employee_count normalized, region encoded as ordinal 0–5 and normalized, founding_year normalized); proxy weight = average of 5 main weights / 3; compute weighted sum; rank descending; return top 5
    - Implement `scoreTreatment(profiles, weights, reasonWeights)`: normalize 5 scoring features only (exclude proxies); compute weighted sum; apply reason-weight boosts from non-goal guardrails (diversity_certified → Strategic boost, disruption_resilience > 7.0 → Resilience boost, relationship_years > 5.0 → Relationship boost); rank descending; return top 5
    - Invert unit_price normalization (1 - normalized) so lower price = higher score
    - Handle edge cases: no suppliers match filters, all weights zero
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 11.1, 11.2, 11.4_

  - [ ]* 4.2 Write property test for min-max normalization bounds
    - **Property 5: Min-Max Normalization Bounds**
    - **Validates: Requirements 3.3**

  - [ ]* 4.3 Write property test for ranking sorted descending
    - **Property 6: Ranking Is Sorted Descending**
    - **Validates: Requirements 3.4**

  - [ ]* 4.4 Write property test for Treatment proxy exclusion
    - **Property 7: Treatment Score Excludes Proxy Features**
    - **Validates: Requirements 3.1, 3.2**

  - [ ]* 4.5 Write property test for reason weight isolation
    - **Property 13: Reason Weight Changes Affect Treatment Only**
    - **Validates: Requirements 11.4**

- [x] 5. Checkpoint — Verify core scoring logic
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement ThresholdEvaluator module
  - [x] 6.1 Implement T1–T5 threshold evaluation with interpretations
    - Implement `evaluate(supplier, params, overrideCounts, datasetMaxDate)` returning an array of ThresholdFire objects
    - T1 (Data Vintage Expiry): fire if supplier has no transactions within `t1_vintage_days` of dataset max date; Laplace: "Over-damped — stale data, sluggish response"; Lyapunov: "Rare regime switching — boundary seldom crossed"
    - T2 (Concentration Risk): fire if `category_spend_share > t2_concentration_pct`; Laplace: "Marginally stable — gain too high"; Lyapunov: "Frequent regime switching — check dwell-time"
    - T3 (High-Value Authority): fire if `avg_total_dollars_obligated > t3_high_value_dollars`; Laplace: "Marginally stable — gain too high"; Lyapunov: "Frequent regime switching — check dwell-time"
    - T4 (Confidence Floor): fire if `normalizedScore < t4_confidence_floor`; Laplace: "Over-damped — low confidence, sluggish"; Lyapunov: "Rare regime switching — boundary seldom crossed"
    - T5 (Override Pattern Detection): fire if supplier overridden ≥ 3 times in session; Laplace: "Gain saturation — repeated override signal"; Lyapunov: "System never leaves escalated regime"
    - Handle edge cases: no date data for T1, spend data unavailable for T2
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 11.5, 11.6_

  - [ ]* 6.2 Write property test for threshold fire conditions
    - **Property 8: Threshold Fires Iff Condition Met**
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5**

- [x] 7. Implement HCICalculator module
  - [x] 7.1 Implement HCI computation with geometric mean formula
    - Implement `compute(params)` returning `{ h_f, h_d, h_r, hci }`
    - H_F = (authorship + documentation + challenge) / 3
    - H_D = position_value from lookup map: pre_execution=1.0, rt_active=0.75, rt_on_demand=0.50, post_execution_review=0.25, post_hoc_audit=0.10, none=0.00
    - H_R = (surfacing + authorization + timeliness) / 3
    - HCI = (H_F × H_D × H_R)^(1/3); if any sub-index is 0, return HCI = 0.000
    - Control fixed params: all zeros, position "rt_on_demand" → HCI = 0.000
    - Treatment fixed params: authorship=1, documentation=0.80, challenge=1, position="rt_active", surfacing=0.90, authorization=0.80, timeliness=0.70 → HCI ≈ 0.824
    - _Requirements: 7.1, 7.2, 7.3, 7.5_

  - [ ]* 7.2 Write property test for HCI geometric mean formula
    - **Property 11: HCI Geometric Mean Formula**
    - **Validates: Requirements 7.3, 7.5**

- [x] 8. Implement SessionManager module
  - [x] 8.1 Implement override tracking and session state
    - Implement `recordOverride(event)` to push an OverrideEvent to the overrides array
    - Implement `recordConfirmation(supplier)` to record a confirmation (no HCI change)
    - Implement `getOverrideCount(supplierId)` to return the number of times a specific supplier has been overridden
    - Implement `getTotalOverrides()` to return total override count
    - Implement `getCurrentAuthorizationBoost()` returning `min(0.05 × totalOverrides, 1.0 - baseAuthorization)` capped so total authorization ≤ 1.0
    - _Requirements: 8.1, 8.2, 8.3, 8.5, 8.6_

  - [ ]* 8.2 Write property test for override authorization boost cap
    - **Property 12: Override Authorization Boost Capped**
    - **Validates: Requirements 8.3**

- [x] 9. Checkpoint — Verify all core modules
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 10. Implement UI Layer
  - [x] 10.1 Implement Procurement Need panel and Data Summary
    - Render category dropdown populated from loaded dataset's distinct categories
    - Render min-budget and max-budget numeric inputs
    - Render supplier-tier filter (LARGE, SMALL, or both)
    - Render "Run Recommendations" button wired to trigger scoring
    - Render Data Summary panel showing transaction count, supplier count, category count
    - Render CSV file-input control for dataset upload with validation error display
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.6, 2.7_

  - [x] 10.2 Implement Side-by-Side panel with difference highlighting
    - Render Control top 5 in left column, Treatment top 5 in right column
    - For each supplier: display name, tier, composite score (3 decimal places), rank position
    - Highlight suppliers added to Treatment (green indicator) and removed from Treatment (red indicator)
    - Display rank change arrows (↑/↓ with green/red) for suppliers in both lists
    - Render difference summary: moved-up count, moved-down count, added count, removed count
    - _Requirements: 3.5, 3.6, 5.1, 5.2, 5.3, 5.4_

  - [ ]* 10.3 Write property test for difference set correctness
    - **Property 9: Difference Sets Are Correct**
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4**

  - [x] 10.4 Implement Scoring Weights and Reason Weights panels
    - Render 5 sliders for scoring features (on_time_delivery_pct, quality_score, unit_price, volume, total_dollars_obligated) defaulting to 0.20, range 0.0–1.0
    - Render 4 sliders for reason weights (Strategic=1.0, Relationship=0.9, Resilience=0.7, Price=0.4), range 0.0–1.0
    - Wire slider changes to recompute both Control and Treatment recommendations and refresh panels
    - Display amber dot indicator next to any parameter that differs from GRD default
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.8_

  - [x] 10.5 Implement Threshold Tuning panel
    - Render numeric inputs for T1 vintage window (days, default 365), T2 concentration limit (%, default 40), T3 high-value cutoff ($, default 500000), T4 confidence floor (0–1, default 0.70)
    - Wire changes to re-evaluate thresholds and update fire indicators
    - Display amber dot for modified thresholds
    - Render "Reset to GRD Defaults" button that restores all weights, reason weights, and threshold values
    - _Requirements: 11.5, 11.6, 11.7, 11.8_

  - [ ]* 10.6 Write property test for reset restoring GRD defaults
    - **Property 14: Reset Restores GRD Defaults**
    - **Validates: Requirements 11.7**

  - [ ]* 10.7 Write property test for modified indicator accuracy
    - **Property 15: Modified Indicator Accuracy**
    - **Validates: Requirements 11.8**

  - [x] 10.8 Implement Threshold Fires panel and Hidden Fields disclosure
    - For each Treatment top-5 supplier, render threshold fire status (T1–T5) with fired/not-fired badge
    - For each fired threshold, display threshold ID, name, Laplace interpretation, and Lyapunov interpretation
    - For each Treatment top-5 supplier, display hidden fields (diversity_certified, relationship_years, buyer_trust_score, disruption_resilience, strategic_alignment) with distinct background styling
    - Display "Buyer Authority Required" badge when strategic_alignment is true
    - Do NOT display hidden fields for Control recommendations
    - _Requirements: 4.6, 4.7, 6.1, 6.2, 6.3, 6.4_

  - [ ]* 10.9 Write property test for strategic alignment badge
    - **Property 10: Strategic Alignment Badge**
    - **Validates: Requirements 6.3**

  - [x] 10.10 Implement HCI Comparison panel
    - Render Control HCI (H_F, H_D, H_R sub-indices and aggregate HCI) in left column
    - Render Treatment HCI (H_F, H_D, H_R sub-indices and aggregate HCI) in right column
    - Display delta between Control and Treatment HCI
    - _Requirements: 7.4_

  - [x] 10.11 Implement Override panel and Session Summary
    - Render "Select" button next to each Treatment top-5 supplier
    - When user selects non-top-ranked supplier: record override, recompute Treatment HCI with authorization boost (+0.05 per override, capped at 1.0), display updated HCI with delta highlighted
    - When user selects top-ranked supplier: record confirmation, display "Confirmed" badge, no HCI change
    - Render session summary: running override count, confirmation count
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

  - [x] 10.12 Implement GRD Summary panel
    - Render collapsible panel showing 5 rules (R1–R5), 5 thresholds (T1–T5) with target fire-rate bands, 3 proxy exclusions with correlation values
    - Display deployment level (Level 2: Automated with Thresholds) and rationale
    - Display 5 residue domains with weights
    - _Requirements: 9.1, 9.2, 9.3_

  - [ ]* 10.13 Write property test for rendered supplier info completeness
    - **Property 16: Rendered Supplier Info Completeness**
    - **Validates: Requirements 3.6**

- [ ] 11. Wire everything together and end-to-end verification
  - [x] 11.1 Connect all modules and verify full page flow
    - Wire UI event handlers to DataLoader, RecommendationEngine, ThresholdEvaluator, HCICalculator, and SessionManager
    - Ensure page loads embedded dataset on open and displays Data Summary
    - Verify full flow: select category → run recommendations → side-by-side display → threshold fires → HCI comparison → override → HCI update
    - Verify weight adjustment flow: change scoring weight → both panels refresh; change reason weight → only Treatment changes
    - Verify CSV upload flow: upload valid CSV → summary updates; upload invalid CSV → error displayed, data retained
    - Verify "Reset to GRD Defaults" restores all parameters
    - Ensure page renders correctly as a single self-contained HTML file with no external dependencies
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [ ]* 11.2 Write integration tests for end-to-end flows
    - Test load → select → run → override → HCI update flow
    - Test weight adjustment → panel refresh flow
    - Test CSV upload → validation → error/success flow
    - _Requirements: 10.1, 10.2, 10.3_

- [x] 12. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- The aggregation script (task 1) is Python; all other code is JavaScript within a single HTML file
- Each task references specific requirements for traceability
- Checkpoints at tasks 5, 9, and 12 ensure incremental validation
- Property tests use fast-check (JavaScript PBT library) per the design's testing strategy
- The embedded dataset is generated once by the Python script and pasted into the HTML file
