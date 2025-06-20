from typing import Any, Dict, List, Optional, Protocol, Type
from pydantic import BaseModel


class IPromptClient(Protocol):
    async def prompt(
        self,
        user_prompt: str,
        system_prompt: Optional[str] = None,
        params: Optional[Dict[str, str]] = None,
        prompt_settings: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Get the response from a prompt."""
        ...  # pragma: no cover

    async def prompt_file(
        self,
        user_prompt_file: str,
        system_prompt: Optional[str] = None,
        params: Optional[Dict[str, str]] = None,
        prompt_settings: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Get the response from a prompt with an input file."""
        ...  # pragma: no cover

    async def prompt_structured(
        self,
        user_prompt: str,
        response_model: Type[BaseModel],
        system_prompt: Optional[str] = None,
        params: Optional[Dict[str, str]] = None,
        prompt_settings: Optional[Dict[str, Any]] = None,
    ) -> BaseModel:
        """Get a structured response from a prompt using Instructor."""
        ...  # pragma: no cover

    async def prompt_file_structured(
        self,
        user_prompt_file: str,
        response_model: Type[BaseModel],
        system_prompt: Optional[str] = None,
        params: Optional[Dict[str, str]] = None,
        prompt_settings: Optional[Dict[str, Any]] = None,
    ) -> BaseModel:
        """Get a structured response from a prompt file using Instructor."""
        ...  # pragma: no cover

    async def embeddings(
        self, inputs: List[str], embedding_settings: Optional[Dict[str, Any]] = None
    ) -> Dict[str, List[float]]:
        """Get embeddings for the given inputs."""
        ...  # pragma: no cover
