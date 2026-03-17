# Deployment Guide

StressLab can now run as a local service or as a containerized workspace server.

## Local service

```bash
stresslab doctor runs
stresslab serve runs --refresh --port 8765 --api-token change-me
```

Open:

- API landing page: `http://127.0.0.1:8765/`
- Browser control center: `http://127.0.0.1:8765/app?token=change-me`

When `--api-token` is set, all non-public endpoints require one of:

- `Authorization: Bearer <token>`
- `X-StressLab-Token: <token>`
- `?token=<token>`

Public endpoints remain:

- `/`
- `/app`
- `/health`

## Docker

Build:

```bash
docker build -t stresslab:latest .
```

Run:

```bash
docker run --rm \
  -p 8765:8765 \
  -e STRESSLAB_API_TOKEN=change-me \
  -v ${PWD}/runs:/data/runs \
  stresslab:latest
```

Then open:

```text
http://127.0.0.1:8765/app?token=change-me
```

## Docker Compose

```bash
docker compose up --build
```

The included `docker-compose.yml` mounts the local `runs/` directory into the container workspace
and exposes port `8765`.

## Operational notes

- The service stores registry data in the workspace root.
- Async job state is persisted in `.stresslab_jobs.sqlite`.
- Job stdout/stderr logs are written to `.stresslab_jobs/logs/`.
- The browser app is a thin client over the same API used by scripts and automation.
