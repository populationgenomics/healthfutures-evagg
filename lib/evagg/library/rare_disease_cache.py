import logging
from collections.abc import Sequence
from typing import Any

from lib.evagg.types import Paper
from lib.evagg.utils.cache import ObjectFileCache

from .rare_disease import RareDiseaseFileLibrary

logger = logging.getLogger(__name__)


class RareDiseaseLibraryCached(RareDiseaseFileLibrary):
    """A class for fetching and categorizing disease papers from PubMed backed by a file-persisted cache."""

    @classmethod
    def serialize_paper_sequence(cls, papers: Sequence[Paper]) -> list[dict[str, Any]]:
        return [paper.props for paper in papers]

    @classmethod
    def deserialize_paper_sequence(cls, data: list[dict[str, Any]]) -> Sequence[Paper]:
        return [Paper(**paper) for paper in data]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        use_previous_cache = kwargs.pop("use_previous_cache", None)
        self._cache = ObjectFileCache[Sequence[Paper]](
            "RareDiseaseFileLibrary",
            serializer=RareDiseaseLibraryCached.serialize_paper_sequence,
            deserializer=RareDiseaseLibraryCached.deserialize_paper_sequence,
            use_previous_cache=use_previous_cache,
        )
        super().__init__(*args, **kwargs)

    async def get_papers(self, query: dict[str, Any]) -> Sequence[Paper]:
        cache_key = f"get_papers_{query['gene_symbol']}"
        if (papers := self._cache.get(cache_key)) is not None:
            logger.info(f"Retrieved {len(papers)} papers from cache for {query['gene_symbol']}.")
            return papers
        papers = await super().get_papers(query)
        self._cache.set(cache_key, papers)
        return papers
