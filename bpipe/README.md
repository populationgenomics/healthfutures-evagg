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
