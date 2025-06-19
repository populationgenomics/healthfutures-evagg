#!/bin/bash
set -e

# Configuration
LITELLM_PORT=4000

# Always use LiteLLM
echo "Starting LiteLLM proxy..."

# Start LiteLLM with config file containing credentials
if [ -f "/app/litellm_config.yaml" ]; then
    # See Dockerfile regarding LITELLM_LOCAL_MODEL_COST_MAP="True".
    LITELLM_LOCAL_MODEL_COST_MAP="True" litellm --config /app/litellm_config.yaml --port $LITELLM_PORT &
else
    echo "ERROR: No litellm_config.yaml file found"
    exit 1
fi

# Wait for LiteLLM to be ready
echo "Waiting for LiteLLM to start..."
for i in {1..30}; do
    if python -c "import urllib.request; urllib.request.urlopen('http://localhost:$LITELLM_PORT/health')" > /dev/null 2>&1; then
        echo "LiteLLM is ready"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "ERROR: LiteLLM failed to start after 30 seconds"
        exit 1
    fi
    sleep 1
done

# Run EvAgg pipeline with LiteLLM proxy URL
echo "Starting EvAgg pipeline..."
OPENAI_BASE_URL="http://localhost:$LITELLM_PORT" run_evagg_app "$@"
