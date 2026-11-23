FROM python:3.11-slim

WORKDIR /app

ARG PETROPID_CODE_COMMIT=v4.2-docker
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=7860 \
    PETROPID_CODE_COMMIT=${PETROPID_CODE_COMMIT}

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

# Ensure benchmark & OWL artifacts are present at build time (strictly offline deterministic)
RUN PETROPID_LLM_DISABLE_DOTENV=1 python 03_models/validate_models.py && PETROPID_LLM_DISABLE_DOTENV=1 python 07_agents/benchmark_runner.py

EXPOSE 7860

CMD ["sh", "-c", "uvicorn app:app --app-dir 08_demo_web --host 0.0.0.0 --port ${PORT:-7860}"]
