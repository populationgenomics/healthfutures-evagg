#!/bin/bash
set -e

# Always use LiteLLM
echo "Starting LiteLLM proxy..."

# Start LiteLLM with environment variables from .env_litellm
if [ -f "/app/.env_litellm" ]; then
    # Source the env file inline for just the litellm command
    (set -a; source /app/.env_litellm; set +a; litellm --config /app/litellm_config.yaml --port 4000) &
else
    echo "ERROR: No .env_litellm file found"
    exit 1
fi

# Wait for LiteLLM to be ready
echo "Waiting for LiteLLM to start..."
for i in {1..30}; do
    if python -c "import urllib.request; urllib.request.urlopen('http://localhost:4000/health')" > /dev/null 2>&1; then
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
OPENAI_BASE_URL="http://localhost:4000" run_evagg_app "$@"
