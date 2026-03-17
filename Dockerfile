FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    STRESSLAB_WORKSPACE=/data/runs \
    STRESSLAB_HOST=0.0.0.0 \
    STRESSLAB_PORT=8765 \
    STRESSLAB_REFRESH=1

WORKDIR /app

COPY . /app

RUN python -m pip install --upgrade pip \
    && pip install .

RUN chmod +x /app/docker-entrypoint.sh

VOLUME ["/data/runs"]

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.getenv(\"STRESSLAB_PORT\", \"8765\")}/health', timeout=3).read()"

ENTRYPOINT ["/app/docker-entrypoint.sh"]
