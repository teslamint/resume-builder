FROM python:3.12-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    pandoc weasyprint fonts-noto-cjk && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENTRYPOINT ["./build.sh"]
