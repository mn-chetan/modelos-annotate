# =============================================================================
# Stage 1: Build Stage
# Uses Chainguard Python 3.12-dev
# =============================================================================
FROM cgr.dev/chainguard/python:3.12-dev AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/venv/bin:$PATH"

WORKDIR /app

RUN python -m venv /app/venv

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

COPY app /app/app
COPY README.md /app/README.md

RUN chown -R 65532:65532 /app

# =============================================================================
# Stage 2: Minimal Production Runtime
# Uses Chainguard Python 3.12 minimal (distroless, non-root)
# =============================================================================
FROM cgr.dev/chainguard/python:3.12

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    PATH="/app/venv/bin:$PATH" \
    PYTHONPATH="/app"

WORKDIR /app

COPY --from=builder --chown=65532:65532 /app/venv /app/venv
COPY --from=builder --chown=65532:65532 /app/app /app/app
COPY --from=builder --chown=65532:65532 /app/README.md /app/README.md

USER 65532

EXPOSE 8000

ENTRYPOINT ["python", "-m", "uvicorn", "app.main:app"]
CMD ["--host", "0.0.0.0", "--port", "8000"]
