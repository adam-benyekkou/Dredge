FROM python:3.11-slim

# Create a non-root user
# We need to create a group with GID 999 (common for docker group on linux hosts)
# or allow passing the GID as an argument
ARG DOCKER_GID=999
RUN groupadd -g ${DOCKER_GID} docker && \
    groupadd -r dredge && \
    useradd -r -g dredge -G docker -d /app -s /sbin/nologin dredge

WORKDIR /app

# Copy dependency specification
COPY pyproject.toml ./

# Copy application code (needed for editable install or package discovery)
COPY app ./app
COPY templates ./templates
COPY static ./static

# Install dependencies
# We install as root to system paths, which is fine for containers
RUN pip install --no-cache-dir . cryptography

# Change ownership of the application directory to the non-root user
# This allows the app to write the SQLite database to /app/dredge.db
RUN chown -R dredge:dredge /app

# Switch to non-root user
USER dredge

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
