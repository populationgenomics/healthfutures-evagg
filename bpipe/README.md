# Evidence Aggregator Bpipe Pipeline

This directory contains the Bpipe pipeline configuration for running Evidence Aggregator in a containerized environment.

## Building the Docker Image

To build the Evidence Aggregator Docker image:

```bash
docker build -t evagg -f Dockerfile ..
```

Note: The build context is set to the parent directory (`..`) to include the entire project.

## Running the Pipeline

The pipeline requires either OpenAI or AWS credentials:

### For OpenAI
 
```bash
export OPENAI_API_KEY="your-api-key"
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

### Running the pipeline

```bash
bpipe run evagg_pipeline.groovy -gene_symbol BRCA1
```

## Model Configuration

The pipeline automatically selects models based on available credentials:

- **OpenAI** (if `OPENAI_API_KEY` is set): `gpt-4.1` and `text-embedding-3-small`
- **AWS Bedrock** (if AWS credentials are set): `bedrock/apac.anthropic.claude-sonnet-4-20250514-v1:0` and `bedrock/amazon.titan-embed-text-v2:0`
