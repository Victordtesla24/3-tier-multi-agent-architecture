FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

# Install uv for deterministic dependency resolution and curl
RUN apt-get update && apt-get install -y curl build-essential git && \
    curl -LsSf https://astral.sh/uv/install.sh | sh && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

# Copy the dependency files first to leverage Docker layer caching
COPY pyproject.toml uv.lock ./

# Install project dependencies
RUN uv sync --all-extras --frozen

# Copy the rest of the architecture
COPY . .

# Set entrypoint to use uv run
ENTRYPOINT ["uv", "run", "python", "src/orchestrator/antigravity-cli.py"]
