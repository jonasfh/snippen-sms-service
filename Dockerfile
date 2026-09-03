# ==============================================================================
# Snippen SMS Gateway Service Dockerfile
# ==============================================================================
FROM python:3.14-slim

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SNIPPEN_SMS_DATABASE_PATH=/app/data/sms_gateway.db \
    SNIPPEN_SMS_LOG_LEVEL=INFO

WORKDIR /app

# Create unprivileged user and persistent data volume directory
RUN groupadd -g 1000 appuser && \
    useradd -u 1000 -g appuser -d /app -s /bin/bash appuser && \
    mkdir -p /app/data && \
    chown -R appuser:appuser /app

# Copy project definition and source code
COPY --chown=appuser:appuser pyproject.toml README.md ./
COPY --chown=appuser:appuser src/ ./src/

# Install application package
RUN pip install --no-cache-dir .

# Switch to unprivileged runtime user
USER appuser

# Declare persistent data volume for SQLite database
VOLUME ["/app/data"]

# Healthcheck verifying database accessibility and gateway readiness
HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=3 \
    CMD snippen-sms status || exit 1

# Default entrypoint runs the SMS gateway daemon
ENTRYPOINT ["snippen-sms"]
CMD ["run"]
