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
        
        // Create .env_litellm file with sensitive environment variables for LiteLLM only.
        // Only include variables that are actually set.
        def envFile = new File(".env_litellm")
        def envContent = []
        
        if (OPENAI_MODEL) envContent << "OPENAI_MODEL=${OPENAI_MODEL}"
        if (OPENAI_EMBEDDING_MODEL) envContent << "OPENAI_EMBEDDING_MODEL=${OPENAI_EMBEDDING_MODEL}"
        if (OPENAI_API_KEY) envContent << "OPENAI_API_KEY=${OPENAI_API_KEY}"
        if (AWS_ACCESS_KEY_ID) envContent << "AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}"
        if (AWS_SECRET_ACCESS_KEY) envContent << "AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}"
        if (AWS_DEFAULT_REGION) envContent << "AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION}"
        
        envFile.text = envContent.join("\n") + "\n"
        // Run the Docker container with mounted volumes.
        // .ref is for processed reference files, which can be shared between different runs.
        exec """
            docker run --rm
                -v ${PWD}/config_mount/genes.yaml:/app/lib/config/queries/genes.yaml:ro
                -v ${PWD}/output_mount:/app/.out
                -v ${PWD}/.env_litellm:/app/.env_litellm
                -v ${PWD}/litellm_config.yaml:/app/litellm_config.yaml:ro
                -v ${PWD}/../.ref:/app/.ref
                ${EVAGG_IMAGE}
                lib/config/evagg_pipeline_curio.yaml

            mv output_mount/evagg_results.json $output
            
            rm -r config_mount output_mount .env_litellm
        """
    }
}

// Run the pipeline
run { 
    run_evagg
}
