# Use official uv image with Python 3.13
FROM ghcr.io/astral-sh/uv:python3.13-bookworm

# Create working directory
WORKDIR /app

# Copy project metadata first (leverages caching)
COPY pyproject.toml uv.lock ./

# Sync dependencies (production only)
RUN uv sync --frozen --no-dev

# Copy application source
COPY src ./src
COPY README.md .

EXPOSE 8000

ENV PYTHONPATH=/app/src

# Activate uv’s venv and run your main script
CMD [".venv/bin/python", "-m", "src.simple_arb"]
