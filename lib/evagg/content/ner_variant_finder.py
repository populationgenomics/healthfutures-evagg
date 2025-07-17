import logging
from collections.abc import Sequence
from typing import Any

from transformers import pipeline

from lib.evagg.utils.cache_dirs import CacheDirectoryManager

from .interfaces import IFindVariants

logger = logging.getLogger(__name__)


class NERVariantFinder(IFindVariants):
    """NER-based variant finder using biomedical NER models."""

    def __init__(
        self,
        cache_dir_manager: CacheDirectoryManager,
        model_name: str = "pruas/BENT-PubMedBERT-NER-Variant",
        confidence_threshold: float = 0.8,
        chunk_size: int = 1000,
        chunk_overlap: int = 100,
    ) -> None:
        """Initialize the NER variant finder.

        Args:
            cache_dir_manager: Cache directory manager for model caching
            model_name: HuggingFace model name for NER
            confidence_threshold: Minimum confidence for extracted variants
            chunk_size: Text chunk size for processing
            chunk_overlap: Overlap between chunks
        """
        self._cache_dir_manager = cache_dir_manager
        self._model_name = model_name
        self._confidence_threshold = confidence_threshold
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._ner_pipeline = None

    def _get_ner_pipeline(self):
        """Lazy initialization of the NER pipeline."""
        if self._ner_pipeline is None:
            cache_dir = self._cache_dir_manager.get_cache_dir("models")
            self._ner_pipeline = pipeline(
                "ner",
                model=self._model_name,
                aggregation_strategy="simple",
                device=None,  # Let transformers auto-detect
                model_kwargs={"cache_dir": cache_dir}
            )
        return self._ner_pipeline

    def _chunk_text(self, text: str) -> list[tuple[str, int]]:
        """Split text into overlapping chunks.

        Args:
            text: Text to chunk

        Returns:
            List of (chunk_text, start_offset) tuples
        """
        chunks = []
        step_size = self._chunk_size - self._chunk_overlap

        for start in range(0, len(text), step_size):
            end = min(start + self._chunk_size, len(text))
            chunks.append((text[start:end], start))
            if end >= len(text):
                break

        return chunks

    def _extract_variants_from_chunk(self, chunk: str, offset: int) -> list[str]:
        """Extract variants from a single text chunk.

        Args:
            chunk: Text chunk to process
            offset: Character offset of chunk in original text

        Returns:
            List of variant strings found in the chunk
        """
        ner = self._get_ner_pipeline()
        variants = []

        try:
            entities = ner(chunk)
            for entity in entities:
                if (entity["entity_group"] in ["B", "I"] and
                    entity["score"] >= self._confidence_threshold):
                    variants.append(entity["word"])
        except Exception as e:
            logger.warning(f"Error processing chunk at offset {offset}: {e}")

        return variants

    async def find_variant_descriptions(
        self, full_text: str, focus_texts: Sequence[str] | None, gene_symbol: str, metadata: dict[str, Any]
    ) -> Sequence[str]:
        """Identify genetic variants relevant to the gene_symbol described in the text.

        Args:
            full_text: Full text of the paper
            focus_texts: Additional focus texts to search
            gene_symbol: Gene symbol to search for variants of
            metadata: Additional metadata for the request

        Returns:
            Sequence of variant descriptions as found in the source text
        """
        all_variants = set()

        # Process full text
        if full_text:
            chunks = self._chunk_text(full_text)
            for chunk, offset in chunks:
                variants = self._extract_variants_from_chunk(chunk, offset)
                all_variants.update(variants)

        # Process focus texts
        if focus_texts:
            for focus_text in focus_texts:
                chunks = self._chunk_text(focus_text)
                for chunk, offset in chunks:
                    variants = self._extract_variants_from_chunk(chunk, offset)
                    all_variants.update(variants)

        # Convert to list and return
        # Note: We don't filter by gene symbol here - that happens downstream
        return list(all_variants)
