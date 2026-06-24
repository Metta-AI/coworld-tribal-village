FROM python:3.12-slim AS builder

RUN apt-get update && \
  apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    curl \
    emscripten \
    git \
    libgl1 && \
  rm -rf /var/lib/apt/lists/*

WORKDIR /workspace/coworld-tribal-village
COPY . .

RUN python -m pip install --no-cache-dir --upgrade pip && \
  python -m pip install --no-cache-dir \
    "numpy>=2.4.6" \
    "fastapi>=0.115.0" \
    "uvicorn[standard]>=0.34.0" \
    "websockets>=15.0.1" && \
  python -c "from tribal_village_env.build import ensure_nim_library_current, ensure_wasm_bundle_current; ensure_nim_library_current(); ensure_wasm_bundle_current()"

FROM python:3.12-slim

RUN apt-get update && \
  apt-get install -y --no-install-recommends \
    ca-certificates \
    libgl1 && \
  rm -rf /var/lib/apt/lists/*

WORKDIR /workspace/coworld-tribal-village
COPY --from=builder /workspace/coworld-tribal-village .

RUN python -m pip install --no-cache-dir --upgrade pip && \
  python -m pip install --no-cache-dir \
    "numpy>=2.4.6" \
    "fastapi>=0.115.0" \
    "uvicorn[standard]>=0.34.0" \
    "websockets>=15.0.1"

ENV COGAME_HOST=0.0.0.0
ENV COGAME_PORT=8080

CMD ["python", "-m", "tribal_village_env.coworld.server"]
