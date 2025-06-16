FROM python:3.13-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Support for custom build steps
COPY README* *build.d /build.d/
RUN bash -c 'for i in $(ls /build.d/*.sh 2>/dev/null | sort) ; do source $i ; done'

# Copy project files
COPY pyproject.toml uv.lock README.md ./
COPY lib ./lib

# Install dependencies and the package, plus LiteLLM proxy
RUN uv sync --frozen --no-dev && \
    uv pip install "litellm[proxy]==1.72.6"

ENV PATH=$PATH:/app/.venv/bin

# Copy startup script
COPY bpipe/run_with_litellm.sh ./
RUN chmod +x ./run_with_litellm.sh

# Use the startup script as entrypoint
ENTRYPOINT ["./run_with_litellm.sh"]
