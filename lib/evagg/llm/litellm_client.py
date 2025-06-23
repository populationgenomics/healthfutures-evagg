import asyncio
import json
import logging
import sys
import time
from functools import lru_cache, reduce
from typing import Any, Dict, Iterable, List, Optional, Type

import instructor
import litellm
from litellm import (
    acompletion, 
    aembedding,
    RateLimitError,
    Timeout,
    APIConnectionError,
    InternalServerError,
    ServiceUnavailableError
)
from litellm.types.utils import ModelResponse
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)
from pydantic import BaseModel, ValidationError
from instructor.exceptions import InstructorRetryException, IncompleteOutputException

from lib.evagg.utils.cache import ObjectCache
from lib.evagg.utils.logging import PROMPT

from .interfaces import IPromptClient

logger = logging.getLogger(__name__)

# aiohttp causes issues on shutdown, maybe because we don't have a long-running event loop:
# the built-in `open` symbol gets garbage collected before the logging handlers want to write files.
litellm.disable_aiohttp_transport = True

class ChatMessages:
    _messages: List[ChatCompletionMessageParam]

    @property
    def content(self) -> str:
        return "".join([json.dumps(message) for message in self._messages])

    def __init__(self, messages: Iterable[ChatCompletionMessageParam]) -> None:
        self._messages = list(messages)

    def __hash__(self) -> int:
        return hash(self.content)

    def insert(self, index: int, message: ChatCompletionMessageParam) -> None:
        self._messages.insert(index, message)

    def to_list(self) -> List[ChatCompletionMessageParam]:
        return self._messages.copy()


class LiteLLMConfig(BaseModel):
    model: str = "gpt-4.1"
    embedding_model: str = "text-embedding-3-small"
    api_key: Optional[str] = "dummy-key"
    base_url: Optional[str] = None
    organization: Optional[str] = None
    max_parallel_requests: int = 0
    timeout: int = 60
    budget_usd: Optional[float] = None  # Optional budget limit in USD


class LiteLLMClient(IPromptClient):
    _config: LiteLLMConfig
    _total_cost: float = 0.0  # Track cumulative cost across all requests

    def __init__(self, config: Dict[str, Any]) -> None:
        self._config = LiteLLMConfig(**config)
        self._total_cost = 0.0
        
        # Log budget configuration at initialization
        if self._config.budget_usd is not None:
            logger.info(f"Cost tracking enabled with budget: ${self._config.budget_usd:.4f}")
        else:
            logger.info("Cost tracking disabled (no budget_usd configured)")

    def _get_completion_kwargs(self) -> Dict[str, Any]:
        """Get common kwargs for LiteLLM completion calls."""
        logger.info(
            f"Using LiteLLM with model {self._config.model}"
            + f" (max_parallel={self._config.max_parallel_requests})."
        )
        
        kwargs = {
            "timeout": self._config.timeout,
        }
        
        if self._config.api_key:
            kwargs["api_key"] = self._config.api_key
            
        if self._config.base_url:
            kwargs["base_url"] = self._config.base_url
            
        if self._config.organization:
            kwargs["organization"] = self._config.organization
            
        return kwargs

    @lru_cache
    def _load_prompt_file(self, prompt_file: str) -> str:
        with open(prompt_file, "r") as f:
            return f.read()

    def _create_completion_task(self, messages: ChatMessages, settings: Dict[str, Any]) -> asyncio.Task:
        """Schedule a completion task to the event loop and return the awaitable."""
        # Use LiteLLM acompletion directly
        completion_kwargs = self._get_completion_kwargs()
        completion_kwargs.update(settings)
        chat_completion = acompletion(
            messages=messages.to_list(), **completion_kwargs
        )
        return asyncio.create_task(chat_completion, name="chat")
    
    def _track_cost_from_completion(self, completion: ModelResponse) -> None:
        """Extract cost from LiteLLM completion object and check budget if cost tracking is enabled.
        
        Args:
            completion: The LiteLLM ModelResponse object
        """
        if self._config.budget_usd is None:
            return
            
        # Access cost via LiteLLM's _hidden_params
        cost = None
        if hasattr(completion, '_hidden_params') and isinstance(completion._hidden_params, dict):
            cost = completion._hidden_params.get('response_cost')
        
        if cost is None:
            logger.error("Cost tracking enabled but no response_cost found in completion._hidden_params")
            raise RuntimeError(
                "Cost tracking is enabled but no response_cost found in LiteLLM completion object"
            )
        
        # Convert to float, handling potential formatting issues
        try:
            cost = float(cost)
        except (ValueError, TypeError):
            raise ValueError(f"Invalid cost value: {cost}")
            
        self._total_cost += cost
        logger.info(f"Request cost: ${cost:.4f}, Total cost: ${self._total_cost:.4f}")
        
        # Check if budget is exceeded
        if self._total_cost > self._config.budget_usd:
            logger.error(
                f"Budget exceeded! Total cost: ${self._total_cost:.4f} > "
                f"Budget: ${self._config.budget_usd:.4f}"
            )
            sys.exit(1)

    async def _generate_completion(self, messages: ChatMessages, settings: Dict[str, Any]) -> str:
        prompt_tag = settings.pop("prompt_tag", "prompt")
        prompt_metadata = settings.pop("prompt_metadata", {})
        connection_errors = 0
        rate_limit_errors = 0

        while True:
            try:
                # Pause 1 second if the number of pending chat completions is at the limit.
                if (max_requests := self._config.max_parallel_requests) > 0:
                    while sum(1 for t in asyncio.all_tasks() if t.get_name() == "chat") > max_requests:
                        await asyncio.sleep(1)

                start_ts = time.time()
                completion = await self._create_completion_task(messages, settings)
                
                # Extract the response content
                response = completion.choices[0].message.content or ""
                elapsed = time.time() - start_ts
                
                # Track cost if budget is enabled using LiteLLM's _hidden_params
                self._track_cost_from_completion(completion)
                
                break
            except (RateLimitError, InternalServerError, ServiceUnavailableError) as e:
                # Only report the first rate limit error not from a proxy unless it's constant.
                if rate_limit_errors > 10 or rate_limit_errors == 0:
                    logger.warning(f"Rate limit error on {prompt_tag}: {e}")
                rate_limit_errors += 1
                await asyncio.sleep(1)
            except (APIConnectionError, Timeout) as e:
                if connection_errors > 2:
                    if self._config.base_url and "localhost" in self._config.base_url:
                        logger.error("LiteLLM API unreachable - have you failed to start a local proxy?")
                    raise
                if connection_errors == 0:
                    logger.warning(f"Connectivity error on {prompt_tag}: {e}")
                connection_errors += 1
                await asyncio.sleep(1)

        prompt_metadata["returned_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        prompt_metadata["elapsed_time"] = f"{elapsed:.1f} seconds"

        prompt_log = {
            "prompt_tag": prompt_tag,
            "prompt_metadata": prompt_metadata,
            "prompt_settings": settings,
            "prompt_text": "\n".join([str(m.get("content")) for m in messages.to_list()]),
            "prompt_response": response,
        }

        logger.log(PROMPT, f"Chat '{prompt_tag}' complete in {elapsed:.1f} seconds.", extra=prompt_log)
        return response

    async def prompt(
        self,
        user_prompt: str,
        system_prompt: Optional[str] = None,
        params: Optional[Dict[str, str]] = None,
        prompt_settings: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Get the response from a prompt."""
        # Replace any '{{${key}}}' instances with values from the params dictionary.
        user_prompt = reduce(lambda x, kv: x.replace(f"{{{{${kv[0]}}}}}", kv[1]), (params or {}).items(), user_prompt)

        messages: ChatMessages = ChatMessages([ChatCompletionUserMessageParam(role="user", content=user_prompt)])
        if system_prompt:
            messages.insert(0, ChatCompletionSystemMessageParam(role="system", content=system_prompt))

        settings = {
            "max_tokens": 1024,
            "temperature": 0.7,
            "model": self._config.model,
            **(prompt_settings or {}),
        }

        return await self._generate_completion(messages, settings)

    async def prompt_file(
        self,
        user_prompt_file: str,
        system_prompt: Optional[str] = None,
        params: Optional[Dict[str, str]] = None,
        prompt_settings: Optional[Dict[str, Any]] = None,
    ) -> str:
        user_prompt = self._load_prompt_file(user_prompt_file)
        return await self.prompt(user_prompt, system_prompt, params, prompt_settings)

    async def prompt_structured(
        self,
        user_prompt: str,
        response_model: Type[BaseModel],
        system_prompt: Optional[str] = None,
        params: Optional[Dict[str, str]] = None,
        prompt_settings: Optional[Dict[str, Any]] = None,
    ) -> Optional[BaseModel]:
        """Get a structured response from a prompt using Instructor.
        
        This method uses the Instructor library to ensure responses match the provided
        Pydantic model schema. It automatically adds JSON schema instructions to the
        prompt and handles validation/retries.
        
        Failure Modes (returns None):
        - Instructor validation failures: When LLM response doesn't match expected schema
        - Incomplete output: When LLM response is truncated before completion
        - Parsing errors: When response cannot be converted to the expected format
        
        Network/API errors (rate limits, timeouts, connection issues) are retried
        automatically and only propagate after multiple failures.
        
        Args:
            user_prompt: The prompt text, which can contain template placeholders
            response_model: Pydantic model class that defines the expected response structure
            system_prompt: Optional system message to set context
            params: Dictionary for template replacement. Keys like 'gene' replace '{{$gene}}' 
                   placeholders in the prompt with actual values like 'ACTC1'
            prompt_settings: Additional settings like temperature, max_tokens, prompt_tag, etc.
        
        Returns:
            An instance of the response_model with validated data from the LLM, or None if
            the LLM response could not be parsed/validated into the expected model structure
            after all retries are exhausted.
        """
        # Replace template placeholders: {{$gene}} -> "ACTC1", {{$variant}} -> "c.123A>T"
        user_prompt = reduce(lambda x, kv: x.replace(f"{{{{${kv[0]}}}}}", kv[1]), (params or {}).items(), user_prompt)

        messages: List[ChatCompletionMessageParam] = [ChatCompletionUserMessageParam(role="user", content=user_prompt)]
        if system_prompt:
            messages.insert(0, ChatCompletionSystemMessageParam(role="system", content=system_prompt))

        settings = {
            "max_tokens": 1024,
            "temperature": 0.7,
            "model": self._config.model,
            **(prompt_settings or {}),
        }

        # Extract logging metadata (these aren't LiteLLM API parameters)
        prompt_tag = settings.pop("prompt_tag", "structured_prompt")
        prompt_metadata = settings.pop("prompt_metadata", {})
        
        # Add completion kwargs to settings
        completion_kwargs = self._get_completion_kwargs()
        settings.update(completion_kwargs)

        # Create instructor client from LiteLLM acompletion
        instructor_client = instructor.from_litellm(acompletion)

        connection_errors = 0
        rate_limit_errors = 0

        while True:
            try:
                # Pause if we're at the parallel request limit
                if (max_requests := self._config.max_parallel_requests) > 0:
                    while sum(1 for t in asyncio.all_tasks() if t.get_name() == "chat") > max_requests:
                        await asyncio.sleep(1)

                start_ts = time.time()
                
                # Use instructor for structured output with completion for cost tracking
                response, completion = await instructor_client.chat.completions.create_with_completion(
                    messages=messages,
                    response_model=response_model,
                    max_retries=2,  # Instructor handles retries on parsing failures
                    **settings
                )
                elapsed = time.time() - start_ts
                
                # Track cost if budget is enabled using LiteLLM's _hidden_params
                self._track_cost_from_completion(completion)
                
                break
                
            except (RateLimitError, InternalServerError, ServiceUnavailableError) as e:
                if rate_limit_errors > 10 or rate_limit_errors == 0:
                    logger.warning(f"Rate limit error on {prompt_tag}: {e}")
                rate_limit_errors += 1
                await asyncio.sleep(1)
            except (APIConnectionError, Timeout) as e:
                if connection_errors > 2:
                    if self._config.base_url and "localhost" in self._config.base_url:
                        logger.error("LiteLLM API unreachable - have you failed to start a local proxy?")
                    raise
                if connection_errors == 0:
                    logger.warning(f"Connectivity error on {prompt_tag}: {e}")
                connection_errors += 1
                await asyncio.sleep(1)
            except InstructorRetryException as e:
                # Check if this is wrapping a retriable error
                original_exception = e.args[0] if e.args else e.__cause__
                
                # If the underlying exception is a rate limit or server error, apply the same retry logic
                if isinstance(original_exception, (RateLimitError, InternalServerError, ServiceUnavailableError)):
                    if rate_limit_errors > 10 or rate_limit_errors == 0:
                        logger.warning(f"Rate limit error (wrapped by Instructor) on {prompt_tag}: {original_exception}")
                    rate_limit_errors += 1
                    await asyncio.sleep(1)
                elif isinstance(original_exception, (APIConnectionError, Timeout)):
                    if connection_errors > 2:
                        if self._config.base_url and "localhost" in self._config.base_url:
                            logger.error("LiteLLM API unreachable - have you failed to start a local proxy?")
                        raise
                    if connection_errors == 0:
                        logger.warning(f"Connectivity error (wrapped by Instructor) on {prompt_tag}: {original_exception}")
                    connection_errors += 1
                    await asyncio.sleep(1)
                else:
                    # If it's a non-retriable error (parsing/validation), return None with detailed logging
                    logger.error(f"Instructor validation failed after all retries for {prompt_tag}: {e}. "
                               f"This indicates the LLM response could not be parsed into the expected {response_model.__name__} format. "
                               f"Original exception: {original_exception}")
                    return None
            except IncompleteOutputException as e:
                logger.error(f"Instructor failed due to incomplete output for {prompt_tag}: {e}. "
                           f"The LLM response was truncated and could not be validated against {response_model.__name__}")
                return None
            except Exception as e:
                logger.error(f"🔍 DEBUG: Uncaught exception type: {type(e).__module__}.{type(e).__name__} - {e}")
                raise

        prompt_metadata["returned_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        prompt_metadata["elapsed_time"] = f"{elapsed:.1f} seconds"

        prompt_log = {
            "prompt_tag": prompt_tag,
            "prompt_metadata": prompt_metadata,
            "prompt_settings": settings,
            "prompt_text": "\n".join([str(m.get("content")) for m in messages]),
            "prompt_response": response.model_dump_json(),  # Log the structured response as JSON
        }

        logger.log(PROMPT, f"Structured chat '{prompt_tag}' complete in {elapsed:.1f} seconds.", extra=prompt_log)
        return response

    async def prompt_file_structured(
        self,
        user_prompt_file: str,
        response_model: Type[BaseModel],
        system_prompt: Optional[str] = None,
        params: Optional[Dict[str, str]] = None,
        prompt_settings: Optional[Dict[str, Any]] = None,
    ) -> Optional[BaseModel]:
        """Get a structured response from a prompt file using Instructor.
        
        Loads the prompt from a file and processes it with structured output validation.
        See prompt_structured() for detailed parameter documentation.
        """
        user_prompt = self._load_prompt_file(user_prompt_file)
        return await self.prompt_structured(user_prompt, response_model, system_prompt, params, prompt_settings)

    async def embeddings(
        self, inputs: List[str], embedding_settings: Optional[Dict[str, Any]] = None
    ) -> Dict[str, List[float]]:
        settings = {"model": self._config.embedding_model, **(embedding_settings or {})}

        embeddings = {}

        async def _run_single_embedding(input: str) -> int:
            connection_errors = 0
            while True:
                try:
                    # Use LiteLLM aembedding directly
                    completion_kwargs = self._get_completion_kwargs()
                    embedding_kwargs = {**settings, **completion_kwargs}
                    
                    result = await aembedding(
                        input=[input], encoding_format="float", **embedding_kwargs
                    )
                    embeddings[input] = result.data[0].embedding
                    
                    # Track cost if budget is enabled using LiteLLM's _hidden_params
                    self._track_cost_from_completion(result)
                    
                    return result.usage.prompt_tokens
                except (RateLimitError, InternalServerError, ServiceUnavailableError) as e:
                    logger.warning(f"Rate limit error on embeddings: {e}")
                    await asyncio.sleep(1)
                except (APIConnectionError, Timeout):
                    if connection_errors > 2:
                        if self._config.base_url and "localhost" in self._config.base_url:
                            logger.error("LiteLLM API unreachable - have you failed to start a local proxy?")
                        raise
                    logger.warning("Connectivity error on embeddings, retrying...")
                    connection_errors += 1
                    await asyncio.sleep(1)

        start_overall = time.time()
        tokens = await asyncio.gather(*[_run_single_embedding(input) for input in inputs])
        elapsed = time.time() - start_overall

        logger.info(f"{len(inputs)} embeddings produced in {elapsed:.1f} seconds using {sum(tokens)} tokens.")
        return embeddings


class LiteLLMCacheClient(LiteLLMClient):
    def __init__(self, config: Dict[str, Any]) -> None:
        # Don't cache tasks that have errored out.
        self.task_cache = ObjectCache[asyncio.Task](lambda t: not t.done() or t.exception() is None)
        super().__init__(config)

    def _create_completion_task(self, messages: ChatMessages, settings: Dict[str, Any]) -> asyncio.Task:
        """Create a new task only if no identical non-errored one was already cached."""
        cache_key = hash((messages.content, json.dumps(settings)))
        if task := self.task_cache.get(cache_key):
            return task
        task = super()._create_completion_task(messages, settings)
        self.task_cache.set(cache_key, task)
        return task
