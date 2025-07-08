# Evidence Aggregator Bpipe Pipeline

This directory contains the Bpipe pipeline configuration for running Evidence Aggregator in a containerized environment using Singularity.

## Building the Singularity Image

To build the Evidence Aggregator Singularity image:

```bash
GIT_HASH=$(git rev-parse --short HEAD)
singularity build evagg-${GIT_HASH}.sif evagg.def
```

## Running the Pipeline

```bash
bpipe run evagg_pipeline.groovy -gene_symbol BRCA1 -output_filename results.json
```
