# Requirements Document

## Introduction

The Live Recommendation Tester is a self-contained, browser-based HTML page that lets a procurement user specify a procurement need (category, budget range, constraints) and instantly see two sets of supplier recommendations side-by-side: one from a standard ML model that uses all visible features including proxy features (Control), and one from a GRT-governed model that excludes proxy features per GRD Rule R2 (Treatment). The page highlights how governance changes recommendations, shows threshold fire status with Laplace/Lyapunov interpretations, computes HCI for both configurations, and allows the user to override a recommendation and observe the HCI impact. The tool loads data from an embedded JSON blob or a user-uploaded CSV file and runs all recommendation logic in JavaScript — no backend is required.

## Glossary

- **Recommendation_Engine**: The JavaScript module that scores and ranks suppliers for a given procurement need using weighted feature scoring
- **Control_Model**: The recommendation configuration that ranks suppliers using all 16 visible features including the 3 proxy features (supplier_employee_count, supplier_hq_region, supplier_founding_year)
- **Treatment_Model**: The recommendation configuration that ranks suppliers using only the 13 non-proxy visible features, excluding proxy features per GRD Rule R2
- **Procurement_Need**: A user-specified query consisting of a category, budget range, and optional constraints
- **Threshold_Evaluator**: The JavaScript module that evaluates the 5 GRD-defined thresholds (T1–T5) against each recommended supplier transaction
- **HCI_Calculator**: The JavaScript module that computes the Human Contribution Index as HCI = (H_F × H_D × H_R)^(1/3)
- **Proxy_Feature**: A visible feature that correlates with the hidden protected attribute (diversity_certified); the 3 declared proxies are supplier_employee_count, supplier_hq_region, and supplier_founding_year
- **Hidden_Field**: A column present in the full dataset but absent from the visible dataset: diversity_certified, relationship_years, buyer_trust_score, disruption_resilience, strategic_alignment
- **Override_Event**: A user action where the buyer selects a different supplier than the one recommended, triggering an HCI recalculation
- **Side_By_Side_Panel**: The UI region that displays Control and Treatment recommendations in adjacent columns for direct comparison
- **Difference_Highlight**: A visual indicator showing which suppliers moved up or down in rank, or were added or removed, between Control and Treatment recommendation lists
- **Tester_Page**: The self-contained HTML page that hosts the entire Live Recommendation Tester application

## Requirements

### Requirement 1: Data Loading

**User Story:** As a procurement analyst, I want to load the supplier transaction dataset into the tester, so that I can run recommendations against real data.

#### Acceptance Criteria

1. THE Tester_Page SHALL embed a default dataset as a JSON object containing all 10,000 transactions with all 21 columns (16 visible + 5 hidden) from procurement_data_full_v4.csv
2. WHEN the user uploads a CSV file via a file-input control, THE Tester_Page SHALL parse the CSV and replace the embedded dataset with the uploaded data
3. WHEN a CSV file is uploaded, THE Tester_Page SHALL validate that the CSV contains the 16 required visible columns (transaction_id, transaction_date, buyer_id, supplier_id, supplier_name, supplier_tier, supplier_employee_count, supplier_hq_region, supplier_founding_year, category, unit_price, volume, total_dollars_obligated, on_time_delivery_pct, quality_score, is_cost_reduction_era)
4. IF a CSV file is missing one or more required columns, THEN THE Tester_Page SHALL display an error message listing the missing column names and retain the previously loaded dataset
5. WHEN a dataset is loaded, THE Tester_Page SHALL display a summary showing the number of transactions, number of unique suppliers, and number of unique categories

### Requirement 2: Procurement Need Specification

**User Story:** As a procurement buyer, I want to specify my procurement need by selecting a category, budget range, and constraints, so that the system can filter and rank relevant suppliers.

#### Acceptance Criteria

1. THE Tester_Page SHALL display a category dropdown populated with the 10 distinct categories extracted from the loaded dataset (Professional Services, IT Hardware, Raw Materials, Office Supplies, Facilities, Logistics, Marketing, HR Services, Legal Services, IT Software)
2. THE Tester_Page SHALL display minimum-budget and maximum-budget numeric input fields that define the budget range for filtering suppliers
3. WHEN the user leaves both budget fields empty, THE Recommendation_Engine SHALL include suppliers across all budget ranges
4. WHEN the user specifies a minimum budget, THE Recommendation_Engine SHALL exclude suppliers whose average total_dollars_obligated for the selected category falls below the minimum
5. WHEN the user specifies a maximum budget, THE Recommendation_Engine SHALL exclude suppliers whose average total_dollars_obligated for the selected category exceeds the maximum
6. THE Tester_Page SHALL display a supplier-tier filter allowing the user to select LARGE, SMALL, or both tiers
7. WHEN the user clicks a "Run Recommendations" button, THE Recommendation_Engine SHALL generate recommendations for the specified procurement need

### Requirement 3: Dual Recommendation Engine

**User Story:** As a procurement analyst, I want to see supplier recommendations from both a standard model and a GRT-governed model side-by-side, so that I can observe how governance changes the recommendations.

#### Acceptance Criteria

1. WHEN the user triggers a recommendation run, THE Recommendation_Engine SHALL compute a composite score for each eligible supplier using the Control_Model (all 16 visible features with equal weighting across on_time_delivery_pct, quality_score, unit_price, volume, and total_dollars_obligated, plus the 3 proxy features)
2. WHEN the user triggers a recommendation run, THE Recommendation_Engine SHALL compute a composite score for each eligible supplier using the Treatment_Model (13 visible features excluding supplier_employee_count, supplier_hq_region, and supplier_founding_year per GRD Rule R2)
3. THE Recommendation_Engine SHALL normalize each scoring feature to a 0–1 range using min-max normalization across the filtered supplier set before computing composite scores
4. THE Recommendation_Engine SHALL rank suppliers by composite score in descending order for both Control_Model and Treatment_Model
5. THE Side_By_Side_Panel SHALL display the top 5 ranked suppliers from the Control_Model in the left column and the top 5 from the Treatment_Model in the right column
6. FOR EACH recommended supplier, THE Side_By_Side_Panel SHALL display the supplier name, supplier tier, composite score (rounded to 3 decimal places), and rank position

### Requirement 4: Threshold Evaluation

**User Story:** As a governance analyst, I want to see which GRD thresholds fired for each recommended supplier, so that I can understand which governance guardrails are active.

#### Acceptance Criteria

1. FOR EACH supplier in the Treatment_Model top 5, THE Threshold_Evaluator SHALL evaluate threshold T1 (Data Vintage Expiry) by checking whether the supplier has no transactions within the most recent 365 days of the dataset
2. FOR EACH supplier in the Treatment_Model top 5, THE Threshold_Evaluator SHALL evaluate threshold T2 (Concentration Risk) by checking whether the supplier accounts for more than 40% of total spend in the selected category
3. FOR EACH supplier in the Treatment_Model top 5, THE Threshold_Evaluator SHALL evaluate threshold T3 (High-Value Authority) by checking whether the supplier's average total_dollars_obligated exceeds $500,000
4. FOR EACH supplier in the Treatment_Model top 5, THE Threshold_Evaluator SHALL evaluate threshold T4 (Confidence Floor) by flagging suppliers whose composite score falls below 0.70 on the normalized scale
5. FOR EACH supplier in the Treatment_Model top 5, THE Threshold_Evaluator SHALL evaluate threshold T5 (Override Pattern Detection) by checking whether the supplier has been overridden 3 or more times in the current session
6. FOR EACH fired threshold, THE Tester_Page SHALL display the threshold ID, name, and a one-line Laplace-domain interpretation (e.g., "Marginally stable — gain too high")
7. FOR EACH fired threshold, THE Tester_Page SHALL display a one-line Lyapunov switched-system interpretation (e.g., "Frequent regime switching — check dwell-time condition")

### Requirement 5: Difference Highlighting

**User Story:** As a procurement analyst, I want to see exactly how governance changed the recommendations, so that I can understand the impact of proxy exclusion and threshold enforcement.

#### Acceptance Criteria

1. WHEN both recommendation lists are displayed, THE Side_By_Side_Panel SHALL highlight suppliers that appear in the Treatment top 5 but not in the Control top 5 with a green visual indicator
2. WHEN both recommendation lists are displayed, THE Side_By_Side_Panel SHALL highlight suppliers that appear in the Control top 5 but not in the Treatment top 5 with a red visual indicator
3. FOR EACH supplier that appears in both top-5 lists, THE Side_By_Side_Panel SHALL display the rank change (e.g., "↑2" or "↓1") with an upward-green or downward-red arrow
4. THE Tester_Page SHALL display a summary count showing: number of suppliers that moved up, number that moved down, number that were added to Treatment, and number that were removed from Treatment

### Requirement 6: Hidden Field Disclosure

**User Story:** As a procurement buyer, I want to see the hidden fields for Treatment recommendations, so that I can understand what contextual information the model cannot access but the buyer should consider.

#### Acceptance Criteria

1. FOR EACH supplier in the Treatment_Model top 5, THE Tester_Page SHALL display the hidden fields from the full dataset: diversity_certified (boolean), relationship_years (numeric), buyer_trust_score (numeric), disruption_resilience (numeric), and strategic_alignment (boolean)
2. THE Tester_Page SHALL visually distinguish hidden fields from visible fields using a distinct background color or border style
3. WHEN a supplier has strategic_alignment equal to true, THE Tester_Page SHALL display a prominent "Buyer Authority Required" badge per GRD Rule R1
4. THE Tester_Page SHALL NOT display hidden fields for Control_Model recommendations, reflecting that the Control model operates without governance-mandated disclosure

### Requirement 7: HCI Computation

**User Story:** As a governance analyst, I want to see the Human Contribution Index for both the Control and Treatment configurations, so that I can quantify how much human judgment each system preserves.

#### Acceptance Criteria

1. WHEN recommendations are displayed, THE HCI_Calculator SHALL compute HCI for the Control_Model using: frame_authorship=0, frame_documentation=0, frame_challenge=0, decision_position="rt_on_demand", residue_surfacing=0, residue_authorization=0, residue_timeliness=0
2. WHEN recommendations are displayed, THE HCI_Calculator SHALL compute HCI for the Treatment_Model using: frame_authorship=1, frame_documentation=0.80, frame_challenge=1, decision_position="rt_active", residue_surfacing=0.90, residue_authorization=0.80, residue_timeliness=0.70
3. THE HCI_Calculator SHALL compute HCI as the geometric mean: HCI = (H_F × H_D × H_R)^(1/3), where H_F = (authorship + documentation + challenge) / 3, H_D = position_value, and H_R = (surfacing + authorization + timeliness) / 3
4. THE Tester_Page SHALL display the HCI score for both Control and Treatment in a comparison panel showing H_F, H_D, H_R sub-indices and the aggregate HCI value
5. IF any sub-index (H_F, H_D, or H_R) equals zero, THEN THE HCI_Calculator SHALL return an HCI of 0.000 for that configuration

### Requirement 8: Override Mechanism

**User Story:** As a procurement buyer, I want to override a recommendation by selecting a different supplier, so that I can see how my judgment affects the HCI score.

#### Acceptance Criteria

1. THE Tester_Page SHALL display a "Select" button next to each supplier in the Treatment_Model top 5 list
2. WHEN the user clicks "Select" on a supplier that is not the top-ranked recommendation, THE Tester_Page SHALL record an override event with the original top-ranked supplier and the user-selected supplier
3. WHEN an override event is recorded, THE HCI_Calculator SHALL recompute the Treatment HCI with residue_authorization increased by 0.05 (capped at 1.0) to reflect the buyer exercising judgment authority
4. WHEN an override event is recorded, THE Tester_Page SHALL display the updated HCI score alongside the previous HCI score with the delta highlighted
5. THE Tester_Page SHALL maintain a running count of override events in the current session, displayed in a session summary panel
6. WHEN the user clicks "Select" on the top-ranked supplier, THE Tester_Page SHALL record a confirmation event (not an override) and display a "Confirmed" badge without changing the HCI score

### Requirement 9: GRD Configuration Display

**User Story:** As a governance analyst, I want to see the GRD configuration that governs the Treatment model, so that I can understand the rules, thresholds, and proxy exclusions in effect.

#### Acceptance Criteria

1. THE Tester_Page SHALL display a collapsible GRD summary panel showing: the 5 rules (R1–R5), the 5 thresholds (T1–T5) with their target fire-rate bands, and the 3 proxy exclusions with their correlation values
2. THE Tester_Page SHALL display the deployment level (Level 2: Automated with Thresholds) and its rationale
3. THE Tester_Page SHALL display the 5 residue domains (organizational, cultural, interpersonal, contextual, experiential) with their weights

### Requirement 10: Self-Contained HTML Page

**User Story:** As a developer, I want the tester to be a single self-contained HTML file with no external dependencies, so that it can be opened directly in a browser without a build step or server.

#### Acceptance Criteria

1. THE Tester_Page SHALL be a single HTML file containing all CSS, JavaScript, and embedded data
2. THE Tester_Page SHALL execute all recommendation logic, threshold evaluation, HCI computation, and UI rendering in client-side JavaScript with no server-side calls
3. THE Tester_Page SHALL render correctly in Chrome, Firefox, and Safari without requiring any browser extensions or plugins
4. THE Tester_Page SHALL use the same visual style (color palette, typography, card layout) as the existing grt_dashboard.html for consistency

### Requirement 11: Adjustable Goal and Rule Weights

**User Story:** As a governance analyst, I want to adjust the goal emphasis weights and rule enforcement levels in real time, so that I can see how different governance configurations change the recommendations.

#### Acceptance Criteria

1. THE Tester_Page SHALL display a "Scoring Weights" panel with sliders for each scoring feature: on_time_delivery_pct, quality_score, unit_price, volume, and total_dollars_obligated, each defaulting to equal weight (0.20) and adjustable from 0.0 to 1.0
2. WHEN the user adjusts a scoring weight slider, THE Recommendation_Engine SHALL recompute both Control and Treatment recommendations using the updated weights and refresh the Side_By_Side_Panel
3. THE Tester_Page SHALL display a "Reason Weights" panel with sliders for the 4 GRD reason categories: Strategic (default 1.0), Relationship (default 0.9), Resilience (default 0.7), and Price (default 0.4), each adjustable from 0.0 to 1.0
4. WHEN the user adjusts a reason weight slider, THE Recommendation_Engine SHALL apply the updated reason weights as score boosts for suppliers matching the corresponding non-goal guardrail in the Treatment_Model only
5. THE Tester_Page SHALL display a "Threshold Tuning" panel with numeric inputs for each threshold value: T1 vintage window (days, default 365), T2 concentration limit (percentage, default 40%), T3 high-value cutoff (dollars, default $500,000), T4 confidence floor (0–1, default 0.70)
6. WHEN the user adjusts a threshold value, THE Threshold_Evaluator SHALL re-evaluate all thresholds against the current recommendations and update the threshold fire indicators
7. THE Tester_Page SHALL display a "Reset to GRD Defaults" button that restores all weights, reason weights, and threshold values to their GRD-declared defaults
8. WHEN any weight or threshold is changed from its default, THE Tester_Page SHALL display a visual indicator (e.g., amber dot) next to the modified parameter showing it differs from the GRD specification
