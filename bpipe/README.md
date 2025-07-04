# Evidence Aggregator Bpipe Pipeline

This directory contains the Bpipe pipeline configuration for running Evidence Aggregator in a containerized environment using Singularity.

## Building the Singularity Image

To build the Evidence Aggregator Singularity image:

```bash
GIT_HASH=$(git rev-parse --short HEAD)
docker build -t evagg:${GIT_HASH} -f Dockerfile ..
singularity build evagg-${GIT_HASH}.sif docker-daemon://evagg:${GIT_HASH}
```

Note: The build context is set to the parent directory (`..`) to include the entire project.

## Running the Pipeline

```bash
bpipe run evagg_pipeline.groovy -gene_symbol BRCA1 -output_filename results.json
```
