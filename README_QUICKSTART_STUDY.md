# Study Quickstart

## Reproduce the flagship study

```powershell
stresslab batch examples/campaigns/flagship_universal_collapse_study.yml --output-dir runs/flagship_universal_collapse_workspace
stresslab theory runs/flagship_universal_collapse_workspace --output-dir runs/flagship_universal_collapse_theory
stresslab research runs/flagship_universal_collapse_workspace --theory-dir runs/flagship_universal_collapse_theory/<theory_run_dir> --output-dir runs/flagship_universal_collapse_research
stresslab batch examples/campaigns/flagship_healthcare_case_study.yml --output-dir runs/flagship_healthcare_case_workspace
python scripts/build_flagship_study_package.py --workspace runs/flagship_universal_collapse_workspace/<batch_run_dir> --theory-dir runs/flagship_universal_collapse_theory/<theory_run_dir> --research-dir runs/flagship_universal_collapse_research/<research_run_dir> --case-dir runs/flagship_healthcare_case_workspace/<case_batch_run_dir> --output-dir artifacts/flagship_universal_collapse_study --manifest examples/campaigns/flagship_universal_collapse_study.yml --case-manifest examples/campaigns/flagship_healthcare_case_study.yml
```

## Reproduce the controlled follow-up

```powershell
python scripts/build_followup_controlled_specs.py --output-root generated/followup_controlled_threshold_study
stresslab batch examples/campaigns/followup_controlled_threshold_study.yml --output-dir runs/followup_controlled_threshold_workspace
stresslab theory runs/followup_controlled_threshold_workspace --output-dir runs/followup_controlled_threshold_theory
stresslab research runs/followup_controlled_threshold_workspace --theory-dir runs/followup_controlled_threshold_theory/<theory_run_dir> --output-dir runs/followup_controlled_threshold_research
python scripts/build_followup_controlled_package.py --workspace runs/followup_controlled_threshold_workspace/<batch_run_dir> --theory-dir runs/followup_controlled_threshold_theory/<theory_run_dir> --research-dir runs/followup_controlled_threshold_research/<research_run_dir> --spec-root generated/followup_controlled_threshold_study --output-dir artifacts/followup_controlled_threshold_study --manifest examples/campaigns/followup_controlled_threshold_study.yml
```

Replace the `<..._run_dir>` placeholders with the timestamped run directories created by the preceding commands.

## Build the free static demo

```powershell
python scripts/build_static_demo_package.py
```

This rebuilds the GitHub Pages-friendly demo library under `docs/assets/static_demo/` and mirrors it into `final_public_package/site/assets/static_demo/`.
