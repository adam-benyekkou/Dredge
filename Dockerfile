# Stage 1: Builder
FROM python:3.11-slim as builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency specification
COPY pyproject.toml ./
# Stub the app package so pip can resolve metadata without the full source.
# The real source is copied in the runtime stage.
RUN mkdir -p app && touch app/__init__.py
# Install dependencies into a local directory
RUN pip install --no-cache-dir --prefix=/install . cryptography

# Stage 2: Runtime
FROM python:3.11-slim as runtime

# Create a non-root user
ARG DOCKER_GID=999
RUN groupadd -g ${DOCKER_GID} docker && \
    groupadd -r dredge && \
    useradd -r -g dredge -G docker -d /app -s /sbin/nologin dredge

WORKDIR /app

# Copy installed dependencies from builder
COPY --from=builder /install /usr/local

# Copy application code and assets
COPY app ./app
COPY templates ./templates
COPY static ./static
COPY scripts/demo_snapshot.db ./scripts/demo_snapshot.db

# Ensure the non-root user owns the application directory
# This is required for the SQLite database (dredge.db)
RUN chown -R dredge:dredge /app

# Switch to non-root user
USER dredge

# Healthcheck using python's built-in urllib to keep image slim
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python3 -c 'import urllib.request; urllib.request.urlopen("http://localhost:8000/health")' || exit 1

# Expose the default FastAPI port
EXPOSE 8000

# Metadata
LABEL maintainer="adam-benyekkou <s.benyekkou@gmail.com>"
LABEL org.opencontainers.image.title="Dredge"
LABEL org.opencontainers.image.description="Docker FinOps & Lifecycle Management Tool"

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
