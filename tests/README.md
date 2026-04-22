# Tests

## Structure

| File | Purpose |
|---|---|
| `test_generate_dataset.py` | Validates dataset generation: row counts, proxy-correlation targets, distribution shape, seed determinism. |
| `test_hci_scorer.py` | Validates HCI scoring: metric bounds [0,1], geometric-mean aggregation, sub-index decomposition. |
| `test_evaluate_models.py` | Validates post-experiment evaluation pipeline. |
| `pre_registration.md` | Pre-registered analysis plan referenced in paper §7.5 — verdict-assignment rules for Claims C1–C5. |

## Running tests

```bash
pytest tests/
```

## Pre-registration

The file `pre_registration.md` documents the analysis plan before the experiment was run. It specifies:

- Verdict-assignment rules for each claim
- Statistical tests used per metric
- Effect-size thresholds
- Multiple-comparison correction

Pre-registration supports the "prove before preach" discipline. Post-hoc analyses, if any, are flagged as such in `RESULTS.md` and in the paper.
