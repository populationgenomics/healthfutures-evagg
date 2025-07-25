import logging
from collections.abc import Sequence
from typing import Any

from lib.evagg.utils.run import set_run_complete

from .interfaces import IEvAggApp, IExtractFields, IGetPapers, IWriteOutput

logger = logging.getLogger(__name__)


class PaperQueryApp(IEvAggApp):
    def __init__(
        self,
        queries: Sequence[dict[str, Any]],
        library: IGetPapers,
        extractor: IExtractFields,
        writer: IWriteOutput,
    ) -> None:
        self._queries = queries
        self._library = library
        self._extractor = extractor
        self._writer = writer

    async def execute(self) -> None:
        output_fieldsets: list[dict[str, str]] = []

        for query in self._queries:
            if not query.get("gene_symbol"):
                raise ValueError("Minimum requirement to search is to input a gene symbol.")
            term = query["gene_symbol"]
            # Get the papers that match this query.
            papers = await self._library.get_papers(query)
            # Assert each returned paper has a unique id
            assert len(papers) == len({p.id for p in papers})
            logger.info(f"Found {len(papers)} papers for {term}")

            # Extract observation fieldsets for each paper.
            for paper in papers:
                extracted_fieldsets = await self._extractor.extract(paper, term)
                output_fieldsets.extend(extracted_fieldsets)

        # Write out the results.
        output_file = await self._writer.write(output_fieldsets)
        set_run_complete(output_file)


class TestApp(IEvAggApp):
    def __init__(self, test_value: Any) -> None:
        self._test_value = test_value

    async def execute(self) -> None:
        if self._test_value == "KeyboardInterrupt":
            raise KeyboardInterrupt("Test app raised KeyboardInterrupt")
        if self._test_value == "Exception":
            raise Exception("Test app raised Exception")
        logger.info(f"Test app executed with value: {self._test_value}")
