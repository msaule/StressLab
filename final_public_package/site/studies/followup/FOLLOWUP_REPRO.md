# Follow-up Study Reproduction

## Commands

```powershell
python scripts/build_followup_controlled_specs.py --output-root generated\followup_controlled_threshold_study
```

```powershell
stresslab batch examples\campaigns\followup_controlled_threshold_study.yml --output-dir runs\followup_controlled_threshold_workspace
```

```powershell
stresslab theory runs\followup_controlled_threshold_workspace\2026-03-17_203951_019840_followup_controlled_threshold_study_batch --output-dir runs\followup_controlled_threshold_theory
```

```powershell
stresslab research runs\followup_controlled_threshold_workspace\2026-03-17_203951_019840_followup_controlled_threshold_study_batch --theory-dir runs\followup_controlled_threshold_theory\2026-03-17_210626_471856_theory_theory --output-dir runs\followup_controlled_threshold_research
```

```powershell
python scripts/build_followup_controlled_package.py --workspace runs\followup_controlled_threshold_workspace\2026-03-17_203951_019840_followup_controlled_threshold_study_batch --theory-dir runs\followup_controlled_threshold_theory\2026-03-17_210626_471856_theory_theory --research-dir runs\followup_controlled_threshold_research\2026-03-17_210822_354767_research_research --spec-root generated\followup_controlled_threshold_study --output-dir C:\Users\saule\Desktop\stresslab\artifacts\followup_controlled_threshold_study --manifest examples\campaigns\followup_controlled_threshold_study.yml
```
