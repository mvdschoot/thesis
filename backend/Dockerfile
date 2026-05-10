FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install \
    "fastapi>=0.115" "uvicorn[standard]>=0.32" "pydantic>=2.7" "pyyaml>=6.0" \
    "langchain>=0.3" "langchain-core>=0.3" "langchain-anthropic>=0.3" "langchain-openai" \
    "python-multipart>=0.0.12"

COPY domain ./domain
COPY pipeline ./pipeline
COPY api ./api
COPY configs ./configs

RUN pip install -e .

EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
