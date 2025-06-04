"""The evagg core library."""

from .app import PaperQueryApp
from .content import PromptBasedContentExtractor, PromptBasedContentExtractorCached
from .interfaces import IEvAggApp, IExtractFields, IGetPapers, IWriteOutput
from .io import JSONOutputWriter, TableOutputWriter
from .library import RareDiseaseFileLibrary, RareDiseaseLibraryCached
from .simple import PropertyContentExtractor, SampleContentExtractor, SimpleFileLibrary
from .truthset import TruthsetFileHandler

__all__ = [
    # Interfaces.
    "IEvAggApp",
    "IGetPapers",
    "IExtractFields",
    "IWriteOutput",
    # App.
    "PaperQueryApp",
    # IO.
    "TableOutputWriter",
    "JSONOutputWriter",
    # Library.
    "SimpleFileLibrary",
    "TruthsetFileHandler",
    "RareDiseaseFileLibrary",
    "RareDiseaseLibraryCached",
    # Content.
    "PromptBasedContentExtractor",
    "PromptBasedContentExtractorCached",
    "PropertyContentExtractor",
    "SampleContentExtractor",
]
