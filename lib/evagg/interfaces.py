from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from lib.evagg.types import Paper


class IEvAggApp(Protocol):
    async def execute(self) -> None:
        """Execute the application."""
        ...  # pragma: no cover


class IGetPapers(Protocol):
    async def get_papers(self, query: dict[str, Any]) -> Sequence[Paper]:
        """Search for papers based on the query."""
        ...  # pragma: no cover


class IExtractFields(Protocol):
    async def extract(self, paper: Paper, gene_symbol: str) -> Sequence[dict[str, str]]:
        """Extract fields from the paper based on the gene_symbol."""
        ...  # pragma: no cover


class IWriteOutput(Protocol):
    async def write(self, output: Sequence[Mapping[str, str]]) -> str | None:
        """Write the output."""
        ...  # pragma: no cover
