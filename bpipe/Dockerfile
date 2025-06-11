FROM python:3.13-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy project files
COPY pyproject.toml uv.lock README.md ./
COPY lib ./lib

# Install dependencies and the package
RUN uv sync --frozen --no-dev

ENV PATH=$PATH:/app/.venv/bin

# Use the package entrypoint
ENTRYPOINT ["run_evagg_app"]
