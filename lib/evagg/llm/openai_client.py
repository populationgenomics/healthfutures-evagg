import asyncio
import json
import logging
import sys
import time
from functools import lru_cache, reduce
from typing import Any, Dict, Iterable, List, Optional

import openai
from openai import AsyncOpenAI
from openai.types import CreateEmbeddingResponse
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)
from pydantic import BaseModel

from lib.evagg.utils.cache import ObjectCache
from lib.evagg.utils.logging import PROMPT

from .interfaces import IPromptClient

logger = logging.getLogger(__name__)


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


class OpenAIConfig(BaseModel):
    model: str = "gpt-4.1"
    embedding_model: str = "text-embedding-3-small"
    api_key: Optional[str] = "dummy-key"
    base_url: Optional[str] = None
    organization: Optional[str] = None
    max_parallel_requests: int = 0
    timeout: int = 60
    budget_usd: Optional[float] = None  # Optional budget limit in USD


class OpenAIClient(IPromptClient):
    _config: OpenAIConfig
    _total_cost: float = 0.0  # Track cumulative cost across all requests

    def __init__(self, config: Dict[str, Any]) -> None:
        self._config = OpenAIConfig(**config)
        self._total_cost = 0.0
        
        # Log budget configuration at initialization
        if self._config.budget_usd is not None:
            logger.info(f"Cost tracking enabled with budget: ${self._config.budget_usd:.4f}")
        else:
            logger.info("Cost tracking disabled (no budget_usd configured)")

    @property
    def _client(self) -> AsyncOpenAI:
        return self._get_client_instance()

    @lru_cache
    def _get_client_instance(self) -> AsyncOpenAI:
        logger.info(
            f"Using OpenAI API with model {self._config.model}"
            + f" (max_parallel={self._config.max_parallel_requests})."
        )
        
        client_options = {
            "timeout": self._config.timeout,
        }
        
        if self._config.api_key:
            client_options["api_key"] = self._config.api_key
            
        if self._config.base_url:
            client_options["base_url"] = self._config.base_url
            
        if self._config.organization:
            client_options["organization"] = self._config.organization
            
        return AsyncOpenAI(**client_options)

    @lru_cache
    def _load_prompt_file(self, prompt_file: str) -> str:
        with open(prompt_file, "r") as f:
            return f.read()

    def _create_completion_task(self, messages: ChatMessages, settings: Dict[str, Any]) -> asyncio.Task:
        """Schedule a completion task to the event loop and return the awaitable."""
        # Always use with_raw_response to get access to headers
        chat_completion = self._client.chat.completions.with_raw_response.create(
            messages=messages.to_list(), **settings
        )
        return asyncio.create_task(chat_completion, name="chat")
    
    def _track_cost_and_check_budget(self, headers: Dict[str, str]) -> None:
        """Extract cost from response headers and check budget if cost tracking is enabled.
        
        Args:
            headers: The response headers dictionary
        """
        logger.debug(f"Budget tracking called - budget_usd: {self._config.budget_usd}")
        logger.debug(f"Response headers: {dict(headers)}")
        
        if self._config.budget_usd is None:
            logger.debug("Skipping cost tracking - no budget configured")
            return
            
        logger.debug("Cost tracking is enabled, checking for cost header")
        
        # Currently only support x-litellm-response-cost header
        cost_header = headers.get('x-litellm-response-cost')
        
        if not cost_header:
            logger.error(f"Cost tracking enabled but x-litellm-response-cost header missing. Available headers: {list(headers.keys())}")
            raise RuntimeError(
                "Cost tracking is enabled but no x-litellm-response-cost header found in response"
            )
        
        logger.debug(f"Found cost header: {cost_header}")
        
        # Convert string to float, handling potential formatting issues
        try:
            cost = float(cost_header)
        except ValueError:
            raise ValueError(f"Invalid cost header value: {cost_header}")
            
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
                raw_response = await self._create_completion_task(messages, settings)
                
                # Extract the actual response and headers
                completion = raw_response.parse()
                response = completion.choices[0].message.content or ""
                elapsed = time.time() - start_ts
                
                # Track cost if budget is enabled (not for error responses)
                self._track_cost_and_check_budget(dict(raw_response.headers))
                
                break
            except (openai.RateLimitError, openai.InternalServerError) as e:
                # Only report the first rate limit error not from a proxy unless it's constant.
                if rate_limit_errors > 10 or rate_limit_errors == 0:
                    logger.warning(f"Rate limit error on {prompt_tag}: {e}")
                rate_limit_errors += 1
                await asyncio.sleep(1)
            except (openai.APIConnectionError, openai.APITimeoutError) as e:
                if connection_errors > 2:
                    if self._config.base_url and "localhost" in self._config.base_url:
                        logger.error("OpenAI API unreachable - have you failed to start a local proxy?")
                    raise
                if connection_errors == 0:
                    logger.warning(f"Connectivity error on {prompt_tag}: {e.message}")
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

    async def embeddings(
        self, inputs: List[str], embedding_settings: Optional[Dict[str, Any]] = None
    ) -> Dict[str, List[float]]:
        settings = {"model": self._config.embedding_model, **(embedding_settings or {})}

        embeddings = {}

        async def _run_single_embedding(input: str) -> int:
            connection_errors = 0
            while True:
                try:
                    # Always use with_raw_response to get access to headers
                    raw_response = await self._client.embeddings.with_raw_response.create(
                        input=[input], encoding_format="float", **settings
                    )
                    result: CreateEmbeddingResponse = raw_response.parse()
                    embeddings[input] = result.data[0].embedding
                    
                    # Track cost if budget is enabled
                    self._track_cost_and_check_budget(dict(raw_response.headers))
                    
                    return result.usage.prompt_tokens
                except (openai.RateLimitError, openai.InternalServerError) as e:
                    logger.warning(f"Rate limit error on embeddings: {e}")
                    await asyncio.sleep(1)
                except (openai.APIConnectionError, openai.APITimeoutError):
                    if connection_errors > 2:
                        if self._config.base_url and "localhost" in self._config.base_url:
                            logger.error("OpenAI API unreachable - have you failed to start a local proxy?")
                        raise
                    logger.warning("Connectivity error on embeddings, retrying...")
                    connection_errors += 1
                    await asyncio.sleep(1)

        start_overall = time.time()
        tokens = await asyncio.gather(*[_run_single_embedding(input) for input in inputs])
        elapsed = time.time() - start_overall

        logger.info(f"{len(inputs)} embeddings produced in {elapsed:.1f} seconds using {sum(tokens)} tokens.")
        return embeddings


class OpenAICacheClient(OpenAIClient):
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
