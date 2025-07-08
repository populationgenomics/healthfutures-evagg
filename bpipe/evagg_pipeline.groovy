// EVAGG Pipeline for processing single gene symbols
// Usage: bpipe run evagg_pipeline.groovy -gene_symbol BRCA1

// Load the default configuration
load 'config.groovy'

// apptainer image file
EVAGG_IMAGE = "$TOOLS/containers/evagg-eab1965.sif"

// LLM configuration
LITELLM_BUDGET_USD = 20.0 // Budget limit in USD
LITELLM_MODEL = "bedrock/apac.anthropic.claude-sonnet-4-20250514-v1:0" // LLM model to use

// AWS configuration
AWS_PROFILE = "aasgard" // AWS profile to use
AWS_DEFAULT_REGION = System.getenv("AWS_DEFAULT_REGION") ?: "ap-southeast-2" // Default to Melbourne region

// Get user's home directory for AWS credentials
USER_HOME = System.properties["user.home"]

options {
    gene_symbol 'Gene symbol to find evidence for', args: 1, required: true
    output_filename 'Output filename, can be used to force a rerun by using unique outputs', args: 1, required: true
}
    
run_evagg = {
    doc "Run EVAGG for a single gene symbol"
    
    produce(opts.output_filename) {
        new File("config_mount").mkdirs()
        new File("output_mount").mkdirs()
        
        // Write the genes.yaml config file, which will be mounted in the container.
        new File("config_mount/genes.yaml").text = """\
- "gene_symbol": "${opts.gene_symbol}"
  "retmax": 25
"""
        
        // Run the container image with mounted volumes.
        // Use `singularity` instead of `apptainer` for backwards compatibility.
        // .ref is for processed reference files, which can be shared between different runs.
        exec """
            singularity run \
                --containall \
                --cleanenv \
                --no-home \
                --writable-tmpfs \
                --pwd /app \
                --bind ${USER_HOME}/.aws/credentials:/root/.aws/credentials:ro \
                --bind ${PWD}/../.ref:/app/.ref \
                --bind ${PWD}/config_mount/genes.yaml:/app/lib/config/queries/genes.yaml:ro \
                --bind ${PWD}/output_mount:/app/.out \
                --env AWS_SHARED_CREDENTIALS_FILE=/root/.aws/credentials \
                --env AWS_PROFILE=${AWS_PROFILE} \
                --env AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION} \
                --env LITELLM_BUDGET_USD=${LITELLM_BUDGET_USD} \
                --env LITELLM_MODEL=${LITELLM_MODEL} \
                ${EVAGG_IMAGE} \
                run_evagg_app lib/config/evagg_pipeline_curio.yaml

            mv output_mount/evagg_results.json $output
            
            rm -r config_mount output_mount
        """
    }
}

// Run the pipeline
run { 
    run_evagg
}
