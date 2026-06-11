# Build Docker.
FROM debian:bookworm-slim AS build

RUN apt-get update && \
  apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    curl \
    git \
    libgl1 && \
  rm -rf /var/lib/apt/lists/*

RUN if [ "$(dpkg --print-architecture)" = "amd64" ]; then \
    curl -fsSL \
      -o /usr/local/bin/nimby \
https://github.com/treeform/nimby/releases/download/0.1.27/nimby-Linux-X64; \
  elif [ "$(dpkg --print-architecture)" = "arm64" ]; then \
    curl -fsSL \
      -o /usr/local/bin/nimby \
https://github.com/treeform/nimby/releases/download/0.1.27/nimby-Linux-ARM64; \
  else \
    echo "unsupported arch: $(dpkg --print-architecture)" && exit 1; \
  fi && \
  chmod +x /usr/local/bin/nimby && \
  nimby use 2.2.10

ENV PATH="/root/.nimby/nim/bin:$PATH"

WORKDIR /workspace/tribal_village
COPY nimby.lock .
RUN nimby sync -g nimby.lock

COPY . .
RUN nim c \
  -d:release \
  -d:useMalloc \
  --opt:speed \
  --stackTrace:on \
  --nimcache:/tmp/villager-nimcache \
  --out:villager \
  players/villager/villager.nim

# Run Docker.
FROM debian:bookworm-slim

RUN apt-get update && \
  apt-get install -y --no-install-recommends \
    ca-certificates \
    libgl1 && \
  rm -rf /var/lib/apt/lists/*

WORKDIR /workspace/tribal_village
COPY --from=build /workspace/tribal_village/villager /bin/villager

CMD ["/bin/villager"]
