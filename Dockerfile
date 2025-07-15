FROM ghcr.io/astral-sh/uv:0.7.19-python3.12-bookworm-slim

WORKDIR /app

# Support for custom build steps
COPY README* *build.d /build.d/
RUN bash -c 'for i in $(ls /build.d/*.sh 2>/dev/null | sort) ; do source $i ; done'

# Copy project files
COPY pyproject.toml uv.lock README.md ./
COPY lib ./lib

# Export dependencies to requirements.txt and install system-wide to use system certs
RUN uv export --frozen --no-hashes --no-dev -o requirements.txt && \
    uv pip install --system -r requirements.txt && \
    uv pip install --system -e .

# Use run_evagg_app directly as entrypoint
ENTRYPOINT ["run_evagg_app"]
