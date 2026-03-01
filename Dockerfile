FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV WORKSPACE_DIR /opt/antigravity

WORKDIR $WORKSPACE_DIR

# Install OS dependencies required for ruamel.yaml and Git manipulation
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies first to cache docker layers
RUN pip install uv
COPY pyproject.toml .
RUN uv pip install --system -e .

# Copy the entire architectural blueprint and logic engine
COPY . .

# Initialize the architecture scaffolding natively
RUN mkdir -p .agent/rules .agent/workflows .agent/tmp .agent/memory docs/architecture

# Set entrypoint to the Python CLI orchestrator
ENTRYPOINT ["python", "src/orchestrator/antigravity-cli.py"]
CMD ["--help"]
