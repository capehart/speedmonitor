FROM python:3.14-slim

ARG TARGETARCH
ARG OOKLA_VERSION=1.2.0
RUN set -eu; \
    case "$TARGETARCH" in \
      arm64) arch=aarch64; sha=3953d231da3783e2bf8904b6dd72767c5c6e533e163d3742fd0437affa431bd3 ;; \
      amd64) arch=x86_64;  sha=5690596c54ff9bed63fa3732f818a05dbc2db19ad36ed68f21ca5f64d5cfeeb7 ;; \
      *) echo "unsupported architecture: $TARGETARCH" >&2; exit 1 ;; \
    esac; \
    python -c "import urllib.request; urllib.request.urlretrieve('https://install.speedtest.net/app/cli/ookla-speedtest-${OOKLA_VERSION}-linux-${arch}.tgz', '/tmp/ookla.tgz')"; \
    echo "$sha  /tmp/ookla.tgz" | sha256sum -c -; \
    tar -xzf /tmp/ookla.tgz -C /usr/local/bin speedtest; \
    rm /tmp/ookla.tgz

COPY src/speedmonitor /app/speedmonitor
WORKDIR /app
USER nobody
ENV HOME=/tmp PYTHONUNBUFFERED=1
EXPOSE 9798
CMD ["python", "-m", "speedmonitor.exporter"]
