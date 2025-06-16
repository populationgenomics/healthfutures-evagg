FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Support for custom build steps
COPY README* *build.d /build.d/
RUN bash -c 'for i in $(ls /build.d/*.sh 2>/dev/null | sort) ; do source $i ; done'

# Copy project files
COPY pyproject.toml uv.lock README.md ./
COPY lib ./lib

# Export dependencies to requirements.txt and install system-wide to use system certs
RUN uv export --frozen --no-hashes --no-dev -o requirements.txt && \
    uv pip install --system -r requirements.txt && \
    uv pip install --system -e . && \
    uv pip install --system "litellm[proxy]==1.72.6"

# Copy startup script
COPY bpipe/run_with_litellm.sh ./
RUN chmod +x ./run_with_litellm.sh

# Use the startup script as entrypoint
ENTRYPOINT ["./run_with_litellm.sh"]
