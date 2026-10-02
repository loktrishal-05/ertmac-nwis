# Always-on public demo: PostGIS + Qdrant + FastAPI + release gateway in one container (Hugging Face Docker Space).
# Synthetic demo data is re-seeded on every boot; nothing is persisted. No LLM: NWIS routes never call one.
FROM python:3.11-slim-bookworm@sha256:a36c24f9cbdf4fd0f52d67f0823eeac19c2028c637cecc392d97f980d4fec56b
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1 git curl ca-certificates \
      nginx postgresql-15 postgresql-15-postgis-3 && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL https://github.com/qdrant/qdrant/releases/download/v1.17.0/qdrant-x86_64-unknown-linux-musl.tar.gz \
      | tar -xz -C /usr/local/bin qdrant
WORKDIR /workbench
COPY backend/requirements-linux.lock /tmp/requirements-linux.lock
RUN pip install --no-cache-dir -r /tmp/requirements-linux.lock
RUN python -c "from huggingface_hub import snapshot_download as d; \
d('BAAI/bge-base-en-v1.5', local_dir='models/bge-base-en-v1.5', allow_patterns=['*.json','vocab.txt','model.safetensors','1_Pooling/*']); \
d('BAAI/bge-reranker-base', local_dir='models/bge-reranker-base', allow_patterns=['*.json','model.safetensors','sentencepiece.bpe.model'])"
COPY backend backend
COPY data/nwis_demo data/nwis_demo
COPY docs/nwis/golden_demo_fixture.json docs/nwis/golden_demo_fixture.json
COPY infra/nwis-release/nginx.conf infra/nwis-release/grant-app.sql infra/nwis-space/start.sh infra/
RUN sed -i 's/server backend:8000;/server 127.0.0.1:8000;/; s/listen 8080;/listen 7860;/' infra/nginx.conf \
    && useradd -m -u 1000 user && chown -R user data && chmod +x infra/start.sh
USER user
ENV PYTHONPATH=/workbench:/workbench/backend:/workbench/backend/tests \
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 HF_HOME=/tmp/huggingface \
    DO_NOT_TRACK=1 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 \
    DATABASE_URL=postgresql+psycopg://nwis_app@127.0.0.1:5432/nwis QDRANT_URL=http://127.0.0.1:6333 \
    MODEL_RUNTIME=ollama MODEL_NAME=qwen3.5:9b PRIMARY_MODEL=qwen3.5:9b \
    MODEL_BASE_URL=http://127.0.0.1:11434 MODEL_ALLOWED_HOSTS=127.0.0.1 \
    WORKBENCH_DATA_ROOT=/workbench/data WORKBENCH_MODEL_ROOT=/workbench/models \
    WORKBENCH_DEPLOYMENT_MODE=public WORKBENCH_SIGNUP_MODE=open WORKBENCH_GOOGLE_ENABLED=false \
    WORKBENCH_CORS_ORIGINS='["https://sovereign-ai-workbench-nine.vercel.app"]' \
    WORKBENCH_AUTH_FRONTEND_ORIGIN=https://sovereign-ai-workbench-nine.vercel.app \
    SESSION_COOKIE_SECURE=true SESSION_COOKIE_NAME=workbench_session SESSION_TTL_SECONDS=28800
EXPOSE 7860
CMD ["/workbench/infra/start.sh"]
