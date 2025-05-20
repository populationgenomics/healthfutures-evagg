# Setup

Evidence Aggregator runs at the Linux command line and depends on access to multiple required and optional external resources. The following document walks you through how to configure your local software and external cloud environment to perform a full-featured execution of an EvAgg [pipeline app](README.md#pipeline-apps).

**_These instructions have been tested on Ubuntu 20.04/22.04 in WSL2 and on Azure VMs_**

## Install software prerequisites

- **Python** 3.12 or above
- **miniconda** with libmamba solver

    ```bash
    curl https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh > miniconda.sh
    sh ./miniconda.sh # close and reopen shell.
    /home/azureuser/miniconda3/bin/conda init $SHELL # if you didn't init conda for your shell during setup.
    conda update -n base -c defaults conda -y
    conda config --add channels conda-forge
    conda install -n base conda-libmamba-solver -y
    conda config --set solver libmamba
    ```

- **git**
- **make** [optional] only for [development tasks](README.md#pre-pr-checks)
- **jq** [optional] only for [development tasks](README.md#pre-pr-checks)

## Clone the repository

Create and enter a local clone of this repository in your runtime environment:

```bash
git clone https://github.com/microsoft/healthfutures-evagg
cd healthfutures-evagg
```

## Build a conda environment

Create a conda environment. All shell commands in this section should be executed from the repository's root directory.

```bash
conda env create -f environment.yml
conda activate evagg
```

## Install poetry dependencies

Use poetry to install the local library and register the pipeline run command:

```bash
poetry install
```

Test installation by running the following. You should see a help message displayed providing usage for the `run_evagg_app` command.

```bash
run_evagg_app -h
```

## Deploy external resources

Evidence Aggregator may need to call out to various external resources (e.g. web endpoints, MongoDB, LLM services) during a given pipeline run. The following sections explain how these resources can be deployed and what settings are available to control how they are accessed during the run. All appropriate resource-specific configuration settings are provided to Evidence Aggregator at pipeline app runtime (as described below in [Configuration settings](#configuration-settings).

## OpenAI API Access

The Evidence Aggregator pipeline requires access to an LLM via the OpenAI API. You can use:

1. **Standard OpenAI API**: Use your API key directly with api.openai.com
2. **LiteLLM Gateway**: Set up a [LiteLLM proxy](https://docs.litellm.ai/docs/proxy/quick_start) to access various providers (Azure OpenAI, Anthropic, etc.)

The pipeline requires a model that supports at least 128k tokens of input context and JSON mode/structured output. Models that meet these requirements include `gpt-4` (`1106-preview` or newer), `gpt-4o`, and `gpt-4o-mini`.
Make sure you have sufficient usage limits or quota (at least 100k TPM or equivalent) for your chosen model.

### Configuration settings for OpenAI

- **OPENAI_MODEL** - The model to use (e.g., `gpt-4-turbo`, `gpt-4o`)
- **OPENAI_API_KEY** - Your OpenAI API key
- **OPENAI_BASE_URL** [optional] - Custom API endpoint for LiteLLM or other services
- **OPENAI_ORGANIZATION** [optional] - Your OpenAI organization ID if applicable
- **OPENAI_MAX_PARALLEL_REQUESTS** [optional] - Controls the maximum number of concurrent requests to the API - leave it out or set to 0 (no max) unless you need to reduce concurrency

### Using LiteLLM to connect to Azure OpenAI or other providers

If you need to use Azure OpenAI or other LLM providers, we recommend using [LiteLLM](https://docs.litellm.ai/) as a proxy server:

1. Install LiteLLM: `pip install litellm`
2. Create a basic configuration file `litellm.config.yaml`:
```yaml
model_list:
  - model_name: gpt-4-turbo
    litellm_params:
      model: azure/gpt-4-turbo
      api_base: https://your-azure-endpoint.openai.azure.com/
      api_key: your-azure-api-key
      api_version: 2024-02-15-preview
```
3. Start the LiteLLM proxy: `litellm --config litellm.config.yaml --port 4000`
4. Configure Evidence Aggregator to use the proxy by setting:
   - `OPENAI_BASE_URL="http://localhost:4000"`
   - `OPENAI_API_KEY="lm-temp"` (a dummy key, as authentication is handled by the proxy)

Refer to the [LiteLLM documentation](https://docs.litellm.ai/docs/proxy/quick_start) for more advanced configurations and options.


## [Optional] MongoDB database

This pipeline makes a substantial number of reference lookup calls to external web resources, most notably NCBI's E-utilities service and the Mutalyzer service.
These calls can contribute substantially to pipeline execution time as access to those web services is rate limited in accordance with their usage guidelines. To speed up repeated execution of identical lookup calls to these services across pipeline runs, Evidence Aggregator can be configured to use a MongoDB instance as a results lookup cache keyed by the full URL/query string of the external service call.

1. Install MongoDB on your local machine or use a hosted MongoDB service:
   - **Local installation**: Follow the [MongoDB installation guide](https://www.mongodb.com/docs/manual/administration/install-community/) for your operating system.
   - **Hosted service**: Use [MongoDB Atlas](https://www.mongodb.com/cloud/atlas/register) to create a free tier cluster.

2. Create a database and collection:
   - Launch the MongoDB shell with `mongosh`
   - Create a database: `use document_cache`
   - Create a collection: `db.createCollection("cache")`
   - Create an index on the id field for faster lookups: `db.cache.createIndex({"id":1}, {unique: true})`

3. (Optional) If you require authentication, create a user with appropriate permissions:
   ```bash
   use document_cache
   db.createUser({
     user: "evagg_user",
     pwd: "your_password",
     roles: [
       { role: "readWrite", db: "document_cache" }
     ]
   })
   ```

### Configuration settings for MongoDB

Configure the following settings in your .env file:

- **EVAGG_CONTENT_CACHE_ENDPOINT** - Set this to your MongoDB server address (e.g., "localhost:27017")
- **EVAGG_CONTENT_CACHE_USERNAME** [optional] - Set this to your MongoDB username if using authentication
- **EVAGG_CONTENT_CACHE_PASSWORD** [optional] - Set this to your MongoDB password if using authentication
- **EVAGG_CONTENT_CACHE_DATABASE** [optional] - Set this to your MongoDB database name (default: "document_cache")
- **EVAGG_CONTENT_CACHE_COLLECTION** [optional] - Set this to your MongoDB collection name (default: "cache")

### Using MongoDB Atlas

If you're using MongoDB Atlas:

1. Create a free cluster on [MongoDB Atlas](https://www.mongodb.com/cloud/atlas/register)
2. Create a database user with readWrite permissions
3. Set up network access to allow connections from your IP address
4. Get your connection string from Atlas (it will look like `mongodb+srv://username:password@cluster.mongodb.net/`)
5. Configure your .env file with:
   - **EVAGG_CONTENT_CACHE_ENDPOINT** - Set this to your MongoDB Atlas hostname (e.g., "cluster.mongodb.net")
   - **EVAGG_CONTENT_CACHE_USERNAME** - Your Atlas database username
   - **EVAGG_CONTENT_CACHE_PASSWORD** - Your Atlas database password

### Note on CosmosDB compatibility

If you are using Azure CosmosDB with the MongoDB API, you can still use this client by configuring it with your CosmosDB connection string that uses the MongoDB API endpoint.

## [Optional] NCBI E-utilities

The pipeline relies heavily on REST API calls to the NCBI E-utilities service, by default throttled on the service side to a maximum of 3 requests per minute. Pipeline execution can be accelerated by obtaining an API key; when the key is provided to E-utilities REST API calls, the max request rate is increased to 10 requests per minute.

See [this page](https://ncbiinsights.ncbi.nlm.nih.gov/2017/11/02/new-api-keys-for-the-e-utilities/) for additional documentation.

### Configuration settings (NCBI E-utilities)

- **NCBI_EUTILS_API_KEY** [optional] - an API KEY for the NCBI E-utilities web resource
- **NCBI_EUTILS_EMAIL** [optional] - an email address associated with this key

## Configuration settings

Once all required and optional external resources have been deployed, the appropriate configuration settings for each resource need to be made available to the pipeline runtime. The default way to do this is through the creation of a `.env` file at the root of your EvAgg repository containing the settings - at runtime, the `lib.evagg.utils.get_dotenv_settings` pipeline utility component can read in resource-specific settings from this file and provide them to the pipeline resource components that need them.

**Note: your `.env` file can potentially contain secrets and should not be committed to source control. The `.env` file is included in `.gitignore` to help prevent this from happening.**

There is a `template.env` file at the repo root that can be used as a starting point for configuring your own local `.env` file. Here is an minimal example `.env` file that can be used for a basic test of pipeline functionality if your AOAI Service Resource is configured for EntraID-based authentication/authorization.

```bash
OPENAI_MODEL="gpt-4-turbo" # or another suitable model
OPENAI_API_KEY="your-openai-api-key"
```

As an alternative to `dotenv` file-based settings, the `lib.evagg.utils.get_env_settings` pipeline utility component is analogous to `get_dotenv_settings` and can be used to read configuration settings in directly from environment variables.

## Configure the pipeline app example

The `lib/config/evagg_pipeline_example.yaml` app spec is a good starting place for your first full-featured execution of the pipeline. By default, this app is configured to use EntraID/RBAC auth for the AOAI Service and no caching for external web lookup calls. The configuration in the various `yaml` specs comprising the app can be modified before running to change the default behavior. For example:

- **For connecting to Azure OpenAI or other services via LiteLLM:** Make sure your LiteLLM proxy is configured and running, and set `OPENAI_BASE_URL` to point to your LiteLLM proxy URL (e.g., `http://localhost:4000`). You can also directly configure the `base_url` in `lib/config/objects/llm.yaml` and `lib/config/objects/llm_cache.yaml` by uncommenting the `base_url` line.
- **For CosmosDB-based caching of external web lookup calls:** Make sure **EVAGG_CONTENT_CACHE_ENDPOINT** is populated in your `.env` file with the appropriate endpoint. Then, in `lib/config/evagg_pipeline_example.yaml`, uncomment the three commented-out lines that terminate in `_cache.yaml` and comment out each of their counterparts. This will swap out the non-caching `lib.evagg.utils.web.RequestsWebContentClient` implementers of `lib.evagg.utils.IWebContentClient` in the default web client sub-specs for the caching implementers in the `_cache.yaml` sub-specs. Each `_cache.yaml` sub-spec (e.g. `lib/config/objects/web_cache.yaml`) ultimately resolves to an instance of `lib.evagg.utils.web.CosmosCachingWebClient` that uses `get_dotenv_settings` to populate its endpoint/auth values from the **EVAGG_CONTENT_CACHE_** values in the `.env` file.
- **For key-based authentication to the CosmosDB cache:** Make sure **EVAGG_CONTENT_CACHE_CREDENTIAL** is populated in your `.env` file with the appropriate key. Then comment out the `credential` section in `lib/config/objects/web_cache.yaml`. Much like the AOAI case above, on `lib.evagg.utils.web.CosmosCachingWebClient` initialization this will leave the `credential` field of the `cache_settings` dictionary empty and force it to use shared key-based auth. In this case the `get_dotenv_settings` provider will have read the key in from the `.env` file and automatically populated the `credential` field in `cache_settings`.

You can create your own pipeline apps by modifying sub-specs as necessary and assembling them into top-level app specs that can be run to produce the desired output with the required runtime configurations. To see an example of a full-featured app spec that uses CosmosDB-based caching and RBAC-based auth for both the AOAI Service and CosmosDB, see `lib/config/evagg_pipeline.yaml`.

## Run the pipeline app example

The script `run_evagg_app` is used to execute a pipeline app. It has one required argument - a pointer to an app spec `yaml` file that implements `lib.evagg.IEvAggApp` - and is invoked from the repository root. To execute the example app as configured above, run the following command. It will perform a PubMed query for a subset of potential papers with two query genes and write the resulting publication evidence table to file in the output directory. In a single test run, the pipeline identified 15 unique observations from a total of 4 publications considered in this configuration.


```bash
run_evagg_app lib/config/evagg_pipeline_example.yaml
```

Using gpt-4o-mini with 2000k TPM of quota allocated, this example will complete in approximately 2 minutes. Results of the run will be located in `.out/run_evagg_pipeline_example_<YYYYMMDD_HHMMSS>`, where each individual run is given a unique datestamp suffix. The primary pipeline output file is `pipeline_benchmark.tsv` contained in that folder. Additional files in the run output folder can be used to debug issues and better understand interactions between the pipeline and the LLM.

You can optionally add or override any leaf value within an app spec dictionary (or sub-dictionary) using the `-o` argument followed by one or more dictionary `key:value` specifications separated by spaces. The following command overrides the default log level for increased logging verbosity and outputs the run results to a file named `different.tsv` in the run output directory:

```bash
run_evagg_app lib/config/evagg_pipeline_example.yaml -o writer.tsv_name:different log.level:DEBUG
```

## Modify the pipeline app example to process genes of interest

The example config used in the step above runs the pipline on a small set of genes that are specified in `lib/config/queries/example_subset.yaml`. In order to process a specific gene or set of genes, one must modify this portion of the pipeline's configuration. Each gene to be processed is specified by a `yaml` block with the following structure:

```yaml
- "gene_symbol": "LRRC10"
  "min_date": "2015/01/01"
  "max_date": "2024/06/01"
  "retmax": 24
```

The only required field in this structure is `gene_symbol`.

The fields `min_date` and `max_date` can optionally be used to constrain the publication date range for the papers to be returned. If not provided, the defaults for the underlying PubMed search API will be used. If `max_date` is provided then `min_date` must also be provided. If `min_date` is provided, `max_date` is not required and will default to today's date.

The `retmax` field can be used to limit the total number of records requested from the underlying PubMed search API. This can be useful in testing scenarios, but can mask relevant results in production scenarios. A warning will be issued by the pipeline if the number of papers specified by `retmax` is equal to the number of papers returned by the PubMed search API as this is suggestive of truncation of results. If no value for `retmax` is provided, the default value for the underlying search API will be used; this is currently 20 records.
