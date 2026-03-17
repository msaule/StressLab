# Discovery Engine

The discovery engine extends StressLab from a resilience-testing tool into a systemic-fragility research lab.

## Pipeline

The implemented pipeline is:

1. generate synthetic systems
2. run baseline simulation
3. run minimum-failure search
4. run worst-case search
5. extract structural and collapse features
6. assemble a campaign dataset
7. rank candidate laws, symbolic laws, and feature importance

## Commands

Generate synthetic systems:

```bash
stresslab generate --count 100 --topology-type mixed
```

Run a full discovery campaign:

```bash
stresslab discover --count 100 --topology-type mixed
stresslab discover --count 100 --topology-type mixed --workers 4
stresslab discover --count 400 --topology-type mixed --shard-count 4 --shard-index 0 --workers 4
stresslab discover --resume-run-dir runs/<discover_dir> --workers 4
```

Analyze an existing discovery dataset:

```bash
stresslab theory runs/<discover_dir>
```

Produce a publication-style report:

```bash
stresslab research runs/<discover_dir>
```

## Synthetic Topologies

The generator currently supports:

- `random_queue`
- `scale_free`
- `small_world`
- `hierarchical_supply`
- `market_microstructure`
- `mixed`

Each generated YAML is a valid `SystemSpec` and includes synthetic search spaces, interventions, and metadata.

## Key Artifacts

`stresslab discover` writes:

- `collapse_dataset.csv`
- `early_warning_dataset.csv`
- `collapse_distribution.csv`
- `feature_importance.csv`
- `candidate_laws.csv`
- `symbolic_laws.csv`
- `batches/collapse_batch_*.csv`
- `fragility_curves.png`
- `cascade_distribution.png`
- `collapse_heatmap.png`
- `law_discovery.png`
- `discovery_report.md`
- `discovery_report.html`

Per-system replay artifacts are also written under `systems/<system_id>/`.

## Batching

Discovery campaigns support batching through `--batch-size`. Intermediate dataset slices are written under `batches/` so larger studies can checkpoint progress instead of relying on one in-memory table.

Discovery campaigns also support parallel execution through `--workers`, which fans out per-system discovery jobs across multiple Python worker processes while keeping deterministic per-system seeds.

For larger studies, `--shard-count` and `--shard-index` split the total requested system count into deterministic shards. Those shard runs can later be merged by pointing `stresslab theory` at the parent workspace directory.

## Flagship Study Pack

StressLab now ships a chained discovery-study manifest at:

- `examples/campaigns/universal_fragility_pipeline.yml`

That campaign runs:

1. `generate`
2. `discover`
3. `theory`
4. `research`

inside one reproducible batch, using batch-time path references such as `{fragility_discover}` to feed later jobs from earlier artifact directories.

Additional domain-flavored study packs are also included:

- `examples/campaigns/healthcare_referral_fragility.yml`
- `examples/campaigns/supply_chain_cascade_study.yml`
- `examples/campaigns/market_microstructure_fragility.yml`
