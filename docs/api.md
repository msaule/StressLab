# API Guide

StressLab ships a lightweight workspace HTTP API through:

```bash
stresslab serve runs --refresh --port 8765
```

The service is intentionally simple: it is file-backed, local-first, and designed to expose the
same artifacts that the CLI writes into a workspace.

The same service also exposes an interactive browser app at `/app`.

## Core endpoints

- `GET /app`
- `GET /health`
- `GET /registry?limit=20`
- `GET /status?limit=25`
- `GET /board?recent_limit=20&watch_limit=12&plan_limit=12`
- `GET /discovery?limit=12`
- `GET /artifacts/<run_id>?expand=1`
- `GET /reports/<run_id>`
- `GET /files/<run_id>/<relative_path>`
- `GET /bundles/<run_id>?include_registry=1`

## Async job endpoints

- `POST /jobs`
- `GET /jobs?limit=20`
- `GET /jobs/<job_id>?expand=1`

The async job queue is persisted in `.stresslab_jobs.sqlite` under the workspace root. Submitted
jobs survive a service restart and any in-flight `running` job is re-queued when the service
starts again.

## Auth

When the service is started with `--api-token`, non-public endpoints require one of:

- `Authorization: Bearer <token>`
- `X-StressLab-Token: <token>`
- `?token=<token>`

Public endpoints remain:

- `/`
- `/app`
- `/health`

Supported async commands:

- `run`
- `generate`
- `discover`
- `theory`
- `research`
- `optimize`
- `evaluate`
- `casebook`
- `benchmark`

## Example submission

```bash
curl -X POST http://127.0.0.1:8765/jobs \
  -H "Content-Type: application/json" \
  -d "{\"command\":\"run\",\"spec_path\":\"examples/healthcare/ed_basic.yml\"}"
```

Example response:

```json
{
  "job_id": "job_abc123def456",
  "status": "queued",
  "command": "run"
}
```

Poll for completion:

```bash
curl http://127.0.0.1:8765/jobs/job_abc123def456?expand=1
```

When a job finishes, the response includes:

- `run_dir`
- `report_path`
- `stdout_path`
- `stderr_path`
- `stdout_tail`
- `stderr_tail`
- `exit_code`
- `error`

## Payload notes

`run` payload:

```json
{
  "command": "run",
  "spec_path": "examples/healthcare/ed_basic.yml"
}
```

`discover` payload:

```json
{
  "command": "discover",
  "count": 200,
  "topology_type": "mixed",
  "shard_count": 4,
  "shard_index": 0,
  "workers": 4
}
```

`optimize` payload:

```json
{
  "command": "optimize",
  "spec_path": "examples/healthcare/ed_basic.yml",
  "budget": 2500,
  "robust": true,
  "scenario_budget": 0.4,
  "scenario_samples": 3,
  "fairness_weight": 0.25
}
```

`evaluate` payload:

```json
{
  "command": "evaluate",
  "spec_path": "examples/healthcare/ed_basic.yml",
  "replicates": 8,
  "budget": 2500,
  "robust": true
}
```

`casebook` payload:

```json
{
  "command": "casebook",
  "suite": "starter",
  "replicates": 2
}
```

## Operational notes

- Async jobs run the same Typer CLI commands that a user would run manually.
- The service writes job stdout/stderr logs into `.stresslab_jobs/logs/`.
- Completed jobs still register their produced artifact directories in the normal workspace
  registry, so `catalog`, `status`, `board`, and the HTTP registry endpoints stay in sync.
