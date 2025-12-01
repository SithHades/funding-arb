FROM python:3.13-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY src/fundings/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire src directory to allow imports from src.fundings...
COPY src /app/src

# Set python path to include /app
ENV PYTHONPATH=/app

# Default command to run Celery worker with Beat
CMD ["celery", "-A", "src.fundings.celery_app", "worker", "--beat", "--loglevel=info"]
