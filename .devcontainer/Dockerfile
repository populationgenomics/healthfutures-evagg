FROM mcr.microsoft.com/devcontainers/python:3.12

ARG USERNAME="vscode"
ENV USER_HOME=/home/${USERNAME}

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy project files
COPY pyproject.toml uv.lock* /tmp/uv-tmp/
COPY lib /tmp/uv-tmp/lib

# Run remaining commands as non-root user.
USER ${USERNAME}

# Set up the project environment
WORKDIR /tmp/uv-tmp
RUN uv sync --dev

# Configure the environment to start correctly.
RUN echo 'export PATH="/tmp/uv-tmp/.venv/bin:$PATH"' >> ${USER_HOME}/.bashrc \
    && echo 'cd /workspaces/healthfutures-evagg' >> ${USER_HOME}/.bashrc
