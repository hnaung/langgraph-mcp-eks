# Multi-stage build — eliminates build tools from runtime image
FROM python:3.12-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Runtime stage — distroless-equivalent slim
FROM python:3.12-slim AS runtime
WORKDIR /app

# Non-root user — never run as UID 0
RUN groupadd -r appgroup && useradd -r -g appgroup -u 1001 appuser

# Copy only installed packages and app code
COPY --from=builder /install /usr/local
COPY --chown=appuser:appgroup . .

# Remove package manager to shrink attack surface
RUN apt-get purge -y --auto-remove curl wget && \
    rm -rf /var/lib/apt/lists/* /tmp/* /root/.cache

USER 1001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import httpx; httpx.get('http://localhost:8080/health').raise_for_status()"

ENTRYPOINT ["python", "-m", "uvicorn", "main:app",
             "--host", "0.0.0.0", "--port", "8080",
             "--no-access-log"]  # Logging via structured JSON, not access log
