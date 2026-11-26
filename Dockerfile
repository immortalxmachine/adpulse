# PySpark needs a JVM. Start from a slim Python image and add a headless JDK 17.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64 \
    ADPULSE_SCALE=ci

# Java 17 (required by Spark 4) + build basics.
RUN apt-get update \
    && apt-get install -y --no-install-recommends openjdk-17-jre-headless \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first (better layer caching), then the package.
COPY requirements.txt requirements-dev.txt pyproject.toml ./
RUN pip install -r requirements.txt
COPY src ./src
COPY sql ./sql
RUN pip install -e . --no-deps

# Default: run the full pipeline at CI scale against SQLite.
CMD ["python", "-m", "adpulse.run", "--scale", "ci"]
