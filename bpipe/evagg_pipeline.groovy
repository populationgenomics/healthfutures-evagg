// EVAGG Pipeline for processing single gene symbols
// Usage: bpipe run evagg_pipeline.groovy -gene_symbol BRCA1

// Configuration
EVAGG_IMAGE = "evagg" // Default Docker image tag
OPENAI_MODEL = "gpt-4.1" // This gets remapped by LiteLLM
OPENAI_EMBEDDING_MODEL = "text-embedding-3-small" // This gets remapped by LiteLLM

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
}
    
run_evagg = {
    doc "Run EVAGG for a single gene symbol"
    
    produce("evagg_results.json") {
        new File("config_mount").mkdirs()
        new File("output_mount").mkdirs()
        
        // Write the genes.yaml config file, which will be mounted in the container.
        new File("config_mount/genes.yaml").text = """\
- "gene_symbol": "${opts.gene_symbol}"
  "retmax": 25
"""
        
        // Create LiteLLM config file with credentials
        def litellmConfig = new File("litellm_config.yaml")
        def configContent = "model_list:\n"
        
        if (hasAWS) {
            configContent += """\
  - model_name: "gpt-*"
    litellm_params:
      model: "bedrock/apac.anthropic.claude-sonnet-4-20250514-v1:0"
      aws_region_name: "${AWS_DEFAULT_REGION}"
      aws_access_key_id: "${AWS_ACCESS_KEY_ID}"
      aws_secret_access_key: "${AWS_SECRET_ACCESS_KEY}"
  - model_name: "text-embedding-*"
    litellm_params:
      model: "bedrock/apac.amazon.titan-embed-text-v2:0"
      aws_region_name: "${AWS_DEFAULT_REGION}"
      aws_access_key_id: "${AWS_ACCESS_KEY_ID}"
      aws_secret_access_key: "${AWS_SECRET_ACCESS_KEY}"
"""
        } else if (hasOpenAI) {
            configContent += """\
  - model_name: "gpt-*"
    litellm_params:
      model: "gpt-4.1"
      api_key: "${OPENAI_API_KEY}"
  - model_name: "text-embedding-*"
    litellm_params:
      model: "text-embedding-3-small"
      api_key: "${OPENAI_API_KEY}"
"""
        }
        
        litellmConfig.text = configContent
        // Run the Docker container with mounted volumes.
        // .ref is for processed reference files, which can be shared between different runs.
        exec """
            docker run --rm
                -v ${PWD}/config_mount/genes.yaml:/app/lib/config/queries/genes.yaml:ro
                -v ${PWD}/output_mount:/app/.out
                -v ${PWD}/litellm_config.yaml:/app/litellm_config.yaml:ro
                -v ${PWD}/../.ref:/app/.ref
                ${EVAGG_IMAGE}
                lib/config/evagg_pipeline_curio.yaml

            mv output_mount/evagg_results.json $output
            
            rm -r config_mount output_mount litellm_config.yaml
        """
    }
}

// Run the pipeline
run { 
    run_evagg
}
