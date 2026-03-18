# Flagship Study Reproduction

## Commands

```powershell
stresslab batch examples\campaigns\flagship_universal_collapse_study.yml --output-dir runs\flagship_universal_collapse_workspace
```

```powershell
stresslab theory runs\flagship_universal_collapse_workspace\2026-03-17_190901_538199_flagship_universal_collapse_study_batch --output-dir runs\flagship_universal_collapse_theory
```

```powershell
stresslab research runs\flagship_universal_collapse_workspace\2026-03-17_190901_538199_flagship_universal_collapse_study_batch --theory-dir runs\flagship_universal_collapse_theory\2026-03-17_194529_983395_theory_theory --output-dir runs\flagship_universal_collapse_research
```

```powershell
stresslab batch examples\campaigns\flagship_healthcare_case_study.yml --output-dir runs\flagship_healthcare_case_workspace
```

```powershell
python scripts/build_flagship_study_package.py --workspace runs\flagship_universal_collapse_workspace\2026-03-17_190901_538199_flagship_universal_collapse_study_batch --theory-dir runs\flagship_universal_collapse_theory\2026-03-17_194529_983395_theory_theory --research-dir runs\flagship_universal_collapse_research\2026-03-17_194839_777454_research_research --case-dir runs\flagship_healthcare_case_workspace\2026-03-17_194529_994433_flagship_healthcare_case_study_batch --output-dir C:\Users\saule\Desktop\stresslab\artifacts\flagship_universal_collapse_study --manifest examples\campaigns\flagship_universal_collapse_study.yml --case-manifest examples\campaigns\flagship_healthcare_case_study.yml
```

## Expected artifact roots

- Discovery workspace: `runs\flagship_universal_collapse_workspace\2026-03-17_190901_538199_flagship_universal_collapse_study_batch`
- Theory analysis: `runs\flagship_universal_collapse_theory\2026-03-17_194529_983395_theory_theory`
- Research analysis: `runs\flagship_universal_collapse_research\2026-03-17_194839_777454_research_research`
- Case study workspace: `runs\flagship_healthcare_case_workspace\2026-03-17_194529_994433_flagship_healthcare_case_study_batch`