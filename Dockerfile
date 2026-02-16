FROM python:3.11-slim

WORKDIR /app

# Copy dependency specification
COPY pyproject.toml ./

# Install dependencies
RUN pip install --no-cache-dir -e .

# Copy application code
COPY app ./app
COPY templates ./templates
COPY static ./static

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
