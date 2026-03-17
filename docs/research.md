# Research Reports

The research layer packages discovery outputs into report-ready scientific artifacts.

## Theory Reports

`stresslab theory <discover_dir>` writes:

- `feature_importance.csv`
- `fragility_models.csv`
- `law_candidates.csv`
- `symbolic_laws.csv`
- `combined_collapse_dataset.csv`
- `source_dataset_index.csv`
- `phase_transition_curve.csv`
- `phase_transition.json`
- `phase_transition_bootstrap.csv`
- `powerlaw_fit.json`
- `tail_model_comparison.csv`
- `early_warning_summary.json`
- `early_warning_trends.csv`
- `theory_report.md`
- `theory_report.html`

It also renders:

- `fragility_curves.png`
- `feature_importance.png`
- `phase_transition.png`
- `collapse_heatmap.png`
- `cascade_distribution.png`
- `law_discovery.png`

## Research Reports

`stresslab research <discover_dir>` builds a publication-style package around the theory layer:

- `research_summary.json`
- `figure_index.csv`
- `research_report.md`
- `research_report.html`
- `figures/`

The `figures/` directory makes the research report portable and self-contained.

The browser control center at `/app` now also includes a Discovery Lab section that surfaces recent
theory and research runs, top symbolic laws, and research figures directly from the workspace API.

## Intended Workflow

For a full study:

```bash
stresslab generate --count 200 --topology-type mixed
stresslab discover --count 200 --topology-type mixed --workers 4
stresslab discover --count 800 --topology-type mixed --shard-count 4 --shard-index 0 --workers 4
stresslab theory runs/<discover_dir>
stresslab theory runs
stresslab research runs/<discover_dir>
stresslab batch examples/campaigns/universal_fragility_pipeline.yml
```

This produces both machine-readable datasets and human-readable scientific outputs for collapse-law exploration.
