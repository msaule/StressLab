# StressLab

StressLab is an open-source systemic fragility lab for queue, flow, and dependency networks.

## The Core Discovery

StressLab's first flagship studies found a clear cross-domain pattern:

> Across domains, collapse thresholds are primarily utilization-led; coupling mainly narrows the failure margin rather than moving the threshold much.

That claim comes from two linked studies:

- A flagship discovery campaign across 5,000 synthetic systems and five topology families
- A controlled follow-up over 2,700 fixed-size synthetic systems plus 144 healthcare variants

![StressLab main result](docs/assets/public/main_result.png)

## Why This Matters

Hospitals, supply chains, and markets are often treated as if they fail for entirely domain-specific reasons. StressLab suggests something more general: many queue-flow-dependency systems share a utilization cliff, and the main operational question is not just "what topology do I have?" but "how close am I to the cliff, and how much shock margin is left?"

That makes StressLab more than a simulator. It is a research and decision engine for collapse dynamics.

## Quick Links

- [Master narrative](MASTER_NARRATIVE.md)
- [Executive summary](MASTER_EXEC_SUMMARY.md)
- [Paper-style abstract](MASTER_ABSTRACT.md)
- [Key findings](MASTER_KEY_FINDINGS.md)
- [Free static demo](docs/demo.html)
- [Study quickstart](README_QUICKSTART_STUDY.md)
- [Public narrative package](final_public_package/INDEX.md)
- [Curated figure set](public_narrative_package/INDEX.md)
- [GitHub Pages-ready site](docs/index.html)

## Free Single-Host Demo

StressLab now includes a fully static demo path that can be hosted entirely on GitHub Pages. It uses a curated library of precomputed scenarios, so visitors can choose a preset, move utilization/coupling/slack/shock controls, and get a nearest-scenario result without running a Python backend.

- Demo page: [docs/demo.html](docs/demo.html)
- Demo library: [docs/assets/static_demo/scenario_library.json](docs/assets/static_demo/scenario_library.json)
- Rebuild command:

```powershell
python scripts/build_static_demo_package.py
```

## What Was Tested

### Flagship cross-domain study

- 5,000 synthetic systems
- 1,000 each for random queue, scale-free, small-world, hierarchical supply, and market microstructure families
- Baseline simulation, minimum-shock failure search, worst-case search, theory extraction, and research reporting

Main result:

- Collapse risk accelerated sharply once baseline utilization entered a shared transition band around `0.10-0.19`
- Median estimated threshold across families: `0.152`
- Shared early-warning signals appeared before failure
- Cascade tails were heavy-tailed, with lognormal fitting better than strict power law

### Controlled follow-up study

- 2,700 fixed-size synthetic systems
- 144 healthcare ED family variants
- Controlled sweeps over utilization and coupling

Main refinement:

- Mean high-versus-low coupling threshold shift: `0.008`
- Largest absolute threshold shift: `0.023`
- Higher coupling reduced the shock margin to failure by about `39.2%`
- Healthcare validation showed collapse turning on around a `0.98x` arrival multiplier and saturating by `1.20x`

## How StressLab Found It

1. Generate large families of synthetic systems with different topology classes.
2. Run deterministic stress campaigns with baseline simulation, minimum-shock failure search, and worst-case stress search.
3. Extract structural features, collapse metrics, early-warning signals, and candidate laws.
4. Build theory and research artifacts that compare collapse behavior across domains.

## Reproduce The Studies

Install:

```bash
pip install -e .
```

For development tools:

```bash
pip install -e .[dev]
```

Run the flagship study:

```powershell
stresslab batch examples/campaigns/flagship_universal_collapse_study.yml --output-dir runs/flagship_universal_collapse_workspace
stresslab theory runs/flagship_universal_collapse_workspace --output-dir runs/flagship_universal_collapse_theory
stresslab research runs/flagship_universal_collapse_workspace --theory-dir runs/flagship_universal_collapse_theory/<theory_run_dir> --output-dir runs/flagship_universal_collapse_research
stresslab batch examples/campaigns/flagship_healthcare_case_study.yml --output-dir runs/flagship_healthcare_case_workspace
```

Run the controlled follow-up:

```powershell
python scripts/build_followup_controlled_specs.py --output-root generated/followup_controlled_threshold_study
stresslab batch examples/campaigns/followup_controlled_threshold_study.yml --output-dir runs/followup_controlled_threshold_workspace
stresslab theory runs/followup_controlled_threshold_workspace --output-dir runs/followup_controlled_threshold_theory
stresslab research runs/followup_controlled_threshold_workspace --theory-dir runs/followup_controlled_threshold_theory/<theory_run_dir> --output-dir runs/followup_controlled_threshold_research
```

For the full packaging commands, see [README_QUICKSTART_STUDY.md](README_QUICKSTART_STUDY.md).

## Platform At A Glance

StressLab still includes the full research and decision stack:

- YAML `SystemSpec` modeling for queue, flow, and dependency systems
- Deterministic discrete-event simulation
- Adversarial stress search
- Robust intervention optimization and controller learning
- Explainability, bottleneck attribution, and reporting
- Synthetic generation, collapse-law discovery, and research packaging
- CLI workflows, campaign orchestration, service API, and browser UI

Core packages:

- [`stresslab/systemspec`](stresslab/systemspec)
- [`stresslab/des`](stresslab/des)
- [`stresslab/search`](stresslab/search)
- [`stresslab/optimize`](stresslab/optimize)
- [`stresslab/generator`](stresslab/generator)
- [`stresslab/theory`](stresslab/theory)
- [`stresslab/discovery`](stresslab/discovery)
- [`stresslab/research`](stresslab/research)
- [`stresslab/service`](stresslab/service)

## Examples

- [`examples/healthcare/ed_basic.yml`](examples/healthcare/ed_basic.yml)
- [`examples/supply_chain/two_supplier_port.yml`](examples/supply_chain/two_supplier_port.yml)
- [`examples/markets/liquidity_withdrawal.yml`](examples/markets/liquidity_withdrawal.yml)
- [`examples/campaigns/flagship_universal_collapse_study.yml`](examples/campaigns/flagship_universal_collapse_study.yml)
- [`examples/campaigns/followup_controlled_threshold_study.yml`](examples/campaigns/followup_controlled_threshold_study.yml)

## Public-Facing Assets

- [Master narrative](MASTER_NARRATIVE.md)
- [Portfolio summary](PORTFOLIO_SUMMARY.md)
- [Demo talk track](DEMO_TALK_TRACK.md)
- [Figure captions](FIGURE_CAPTIONS.md)
- [Frontend handoff spec](FRONTEND_V1_SPEC.md)
- [Final public package](final_public_package/INDEX.md)

## Repository Structure

```text
stresslab/
  stresslab/
  examples/
  tests/
  docs/
  artifacts/
  public_narrative_package/
  final_public_package/
  notebooks/
```

## Contributing

StressLab favors correctness before performance and clarity before cleverness.

```bash
pip install -e .[dev]
ruff check .
pytest
```

## License

[MIT](LICENSE)
