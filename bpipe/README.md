# Evidence Aggregator Bpipe Pipeline

This directory contains the Bpipe pipeline configuration for running Evidence Aggregator in a containerized environment using apptainer.

## Building the apptainer Image

To build the Evidence Aggregator apptainer image:

```bash
# Get the semantic version from pyproject.toml
VERSION=$(grep '^version = ' ../pyproject.toml | cut -d'"' -f2)
module load apptainer
apptainer build evagg-${VERSION}.sif evagg.def
```

## Running the Pipeline

```bash
bpipe run evagg_pipeline.groovy -gene_symbol BRCA1 -output_filename results.json
```

### For OpenAI

```bash
export OPENAI_API_KEY="your-api-key"
export OPENAI_BASE_URL="http://localhost:8080"  # For llama.cpp server
```

### For AWS Bedrock

```bash
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export AWS_REGION_NAME="us-east-1"
```

If you have profiles / credentials set up in `~/.aws`, you can set `$AWS_PROFILE` and run:

```bash
eval $(aws configure export-credentials --profile $AWS_PROFILE --format env)
```
