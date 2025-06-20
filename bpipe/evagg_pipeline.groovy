// EVAGG Pipeline for processing single gene symbols
// Usage: bpipe run evagg_pipeline.groovy -gene_symbol BRCA1

// Configuration
EVAGG_IMAGE = "evagg" // Default Docker image tag
LITELLM_BUDGET_USD = 20.0 // Budget limit in USD

// Check for either OpenAI or AWS credentials
OPENAI_API_KEY = System.getenv("OPENAI_API_KEY")
AWS_ACCESS_KEY_ID = System.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = System.getenv("AWS_SECRET_ACCESS_KEY")
AWS_DEFAULT_REGION = System.getenv("AWS_DEFAULT_REGION") ?: "ap-southeast-2" // Default to Melbourne region

// At least one set of credentials must be available
boolean hasOpenAI = OPENAI_API_KEY != null
boolean hasAWS = AWS_ACCESS_KEY_ID && AWS_SECRET_ACCESS_KEY

if (!hasOpenAI && !hasAWS) {
    throw new RuntimeException("Either OPENAI_API_KEY or AWS credentials (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY) must be set")
}

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
        
        // Create environment file with credentials (for Docker --env-file)
        def envFile = new File(".env")
        def envContent = "LITELLM_BUDGET_USD=${LITELLM_BUDGET_USD}\n"
        
        if (hasAWS) {
            envContent += """\
LITELLM_MODEL=bedrock/apac.anthropic.claude-sonnet-4-20250514-v1:0
AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}
AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}
AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION}
"""
        } else if (hasOpenAI) {
            envContent += """\
LITELLM_MODEL=gpt-4.1
LITELLM_API_KEY=${OPENAI_API_KEY}
"""
        }
        
        envFile.text = envContent
        // Run the Docker container with mounted volumes.
        // .ref is for processed reference files, which can be shared between different runs.
        exec """
            docker run --rm
                --env-file ${PWD}/.env
                -v ${PWD}/config_mount/genes.yaml:/app/lib/config/queries/genes.yaml:ro
                -v ${PWD}/output_mount:/app/.out
                -v ${PWD}/../.ref:/app/.ref
                ${EVAGG_IMAGE}
                lib/config/evagg_pipeline_curio.yaml

            mv output_mount/evagg_results.json $output
            
            rm -r config_mount output_mount .env
        """
    }
}

// Run the pipeline
run { 
    run_evagg
}
