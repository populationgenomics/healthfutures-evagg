// EVAGG Pipeline for processing single gene symbols
// Usage: bpipe run evagg_pipeline.groovy -gene_symbol BRCA1

// Load the default configuration
load 'config.groovy'


options {
    gene_symbol 'Gene symbol to find evidence for', args: 1, required: true
    output_filename 'Output filename, can be used to force a rerun by using unique outputs', args: 1, required: true
    evagg_version 'EvAgg container version to use', args: 1, required: true
    model 'LLM model to use', args: 1, required: true
}
    
run_evagg = {
    doc "Run EVAGG for a single gene symbol"
    
    produce(opts.output_filename) {
        // Build image path from version
        def evaggImage = "$TOOLS/containers/evagg-${opts.evagg_version}.sif"
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
                --bind ${PWD}/../.ref:/app/.ref \
                --bind ${PWD}/config_mount/genes.yaml:/app/lib/config/queries/genes.yaml:ro \
                --bind ${PWD}/output_mount:/app/.out \
                --env OPENAI_MODEL=${opts.model} \
                ${evaggImage} \
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
