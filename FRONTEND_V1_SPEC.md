# Frontend V1 Spec

## Purpose

Frontend V1 should be a thin public demo on top of the existing StressLab outputs and service layer. It does not need to expose the full platform. Its goal is to let someone understand the main research result and explore one or two live what-if scenarios without learning the whole repository.

## Core User Story

A visitor chooses a domain preset, adjusts a small set of interpretable knobs, runs a preset stress scenario, and sees:

- collapse risk
- failure margin
- likely bottlenecks
- the best available intervention or playbook

## Proposed Presets

- Healthcare ED
- Supply chain port disruption
- Market liquidity withdrawal
- Synthetic generic network

## Controls

- Utilization
- Coupling
- Slack or buffer margin
- Shock intensity

These map cleanly to existing StressLab spec/intervention surfaces and to the results already shown in the flagship studies.

## UX Flow

1. Landing panel explains the main discovery in one sentence.
2. User picks a preset domain card.
3. User adjusts two to four sliders.
4. User clicks "Run stress test."
5. UI shows:
   - collapse risk gauge
   - threshold or failure-margin indicator
   - bottleneck list
   - recommended intervention
   - one trace figure or system comparison figure
6. Optional "Why?" panel expands to show the research-backed rationale.

## What Should Be Truly Computed Live

- Preset `stresslab run` or `stresslab optimize` executions for a small number of parameterized scenarios
- Collapse risk, bottleneck summaries, and intervention outputs
- Existing report figures where runtime is acceptable

## What Should Be Precomputed

- Flagship study figures
- Follow-up study figures
- Cross-domain collapse overlays
- Static captions and narrative copy
- Any large discovery or theory outputs

## Existing Backend Surfaces To Reuse

- `stresslab serve`
- `/jobs`
- `/jobs/<id>`
- `/artifacts/<run_id>`
- `/reports/<run_id>`
- `/files/<run_id>/<relative_path>`

The thin frontend should wrap existing commands rather than introducing a new computation layer.

## Suggested Command Wrappers

- `stresslab run <preset>`
- `stresslab search <preset> --objective min_failure`
- `stresslab optimize <preset> --budget <preset_budget>`

For MVP, it is acceptable to expose preset-backed wrappers rather than free-form arbitrary YAML editing.

## MVP Scope

- One landing page
- One preset selector
- Three sliders
- One run button
- One result page
- One figure panel
- One bottleneck/intervention summary panel

## Non-Goals For V1

- Arbitrary system editing
- Large discovery campaigns
- Full workspace management
- Multi-user state
- Full artifact browser

## Success Criteria

- A new visitor can understand StressLab's main result in under one minute.
- A demo operator can run a convincing live scenario in under three minutes.
- The UI clearly connects the research result to an intuitive operational case.
