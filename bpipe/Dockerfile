FROM continuumio/miniconda3:25.3.1-1

WORKDIR /app

# Copy files from parent directory (context will be set to parent)
COPY environment.yml .

# Set up conda environment
RUN conda config --add channels conda-forge && \
    conda install -n base conda-libmamba-solver && \
    conda config --set solver libmamba && \
    conda env update -n base -f environment.yml && \
    conda clean -afy

# Copy only the files needed for poetry installation
COPY pyproject.toml poetry.toml ./
COPY lib ./lib

# Install the package with poetry and LiteLLM
RUN poetry install --no-interaction && \
    pip install litellm[proxy]==1.72.1 && \
    rm -rf /root/.cache/pip

# Copy startup script
COPY bpipe/run_with_litellm.sh /run_with_litellm.sh
RUN chmod +x /run_with_litellm.sh

# Use the startup script as entrypoint
ENTRYPOINT ["/run_with_litellm.sh"]
