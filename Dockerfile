FROM python:3.11-slim

WORKDIR /app

# Copy dependency specification
COPY pyproject.toml ./

# Copy application code (needed for editable install or package discovery)
COPY app ./app
COPY templates ./templates
COPY static ./static

# Install dependencies
RUN pip install --no-cache-dir .

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
