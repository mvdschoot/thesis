# One image for every service — compose overrides `command` to pick the
# entrypoint per container. Keeps the build cache shared.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps Kafka client may want
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first (cacheable layer).
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install \
    "fastapi>=0.115" "uvicorn[standard]>=0.32" "pydantic>=2.7" "pyyaml>=6.0" \
    "aiokafka>=0.11" \
    "langchain>=0.3" "langchain-core>=0.3" "langchain-anthropic>=0.3" \
    "python-multipart>=0.0.12"

# Project source.
COPY shared ./shared
COPY services ./services
COPY configs ./configs

# Make the local packages importable.
RUN pip install -e .

# Default to the gateway. Compose overrides this for each worker.
EXPOSE 8000
CMD ["uvicorn", "services.gateway.app:app", "--host", "0.0.0.0", "--port", "8000"]
