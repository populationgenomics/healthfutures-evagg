import hashlib
import json
import logging
import urllib.parse
from typing import Any, Callable, Dict, List, Optional, Tuple

import pymongo
import requests
from defusedxml import ElementTree
from pydantic import BaseModel, Extra, validator
from pymongo.collection import Collection
from requests.adapters import HTTPAdapter, Retry

from .interfaces import IWebContentClient

logger = logging.getLogger(__name__)

CONTENT_TYPES = ["text", "json", "xml"]


class WebClientSettings(BaseModel, extra=Extra.forbid):
    max_retries: int = 0  # no retries by default
    retry_backoff: float = 0.5  # indicates progression of 0.5, 1, 2, 4, 8, etc. seconds
    retry_codes: List[int] = [429, 500, 502, 503, 504]  # rate-limit exceeded, server errors
    no_raise_codes: List[int] = []  # don't raise exceptions for these codes
    content_type: str = "text"
    timeout: float = 15.0  # seconds
    status_code_translator: Optional[Callable[[str, int, str], Tuple[int, str]]] = None

    @validator("content_type")
    @classmethod
    def _validate_content_type(cls, value: str) -> str:
        if value not in CONTENT_TYPES:
            raise ValueError(f"Web content type must be one of {'/'.join(CONTENT_TYPES)}, got '{value}'")
        return value


class RequestsWebContentClient(IWebContentClient):
    """A web content client that uses the requests/urllib3 libraries."""

    def __init__(self, settings: Optional[Dict[str, Any]] = None) -> None:
        self._settings = WebClientSettings(**settings) if settings else WebClientSettings()
        self._session: Optional[requests.Session] = None
        self._get_status_code = self._settings.status_code_translator or (lambda _, c, s: (c, s))

    def _get_session(self) -> requests.Session:
        """Get the session, initializing it if necessary."""
        if self._session is None:
            self._session = requests.Session()
            retries = Retry(
                total=self._settings.max_retries,
                backoff_factor=self._settings.retry_backoff,
                status_forcelist=self._settings.retry_codes,
            )
            self._session.mount("https://", HTTPAdapter(max_retries=retries))
            self._session.mount("http://", HTTPAdapter(max_retries=retries))
        return self._session

    def _raise_for_status(self, code: int) -> None:
        """Raise an exception if the status code is not 2xx."""
        if code >= 400 and code < 600 and code not in self._settings.no_raise_codes:
            response = requests.Response()
            response.status_code = code
            raise requests.HTTPError(f"Request failed with status code {code}", response=response)

    def _transform_content(self, text: str, content_type: Optional[str]) -> Any:
        """Get the content from the response based on the provided content type."""
        content_type = content_type or self._settings.content_type
        if content_type == "text":
            return text
        elif content_type == "json":
            return json.loads(text) if text else {}
        elif content_type == "xml":
            return ElementTree.fromstring(text) if text else None
        else:
            raise ValueError(f"Invalid content type: {content_type}")

    def _get_content(self, url: str, data: Optional[Dict[str, Any]] = None) -> Tuple[int, str]:
        """GET (or POST) the text content at the provided URL."""
        if data is not None:
            response = self._get_session().post(url, json=data, timeout=self._settings.timeout)
        else:
            response = self._get_session().get(url, timeout=self._settings.timeout)
        return self._get_status_code(url, response.status_code, response.text)

    def update_settings(self, **kwargs: Any) -> None:
        """Update the default values for the session."""
        updated_settings = {**self._settings.dict(), **kwargs}
        self._settings = WebClientSettings(**updated_settings)
        self._session = None  # reset the session to apply the new settings

    def get(
        self,
        url: str,
        data: Optional[Dict[str, Any]] = None,
        content_type: Optional[str] = None,
        url_extra: Optional[str] = None,
    ) -> Any:
        """GET (or POST) the content at the provided URL."""
        code, content = self._get_content(url + (url_extra or ""), data)
        self._raise_for_status(code)
        return self._transform_content(content, content_type)


class CacheClientSettings(BaseModel, extra=Extra.forbid):
    endpoint: str
    username: Optional[str] = None
    password: Optional[str] = None
    database: str = "document_cache"
    collection: str = "cache"
    no_cache_codes: List[int] = []


class MongoDBCachingWebClient(RequestsWebContentClient):
    """A web content client that uses a lookaside MongoDB cache."""

    def __init__(self, cache_settings: Dict[str, Any], web_settings: Optional[Dict[str, Any]] = None) -> None:
        self._cache_settings = CacheClientSettings(**cache_settings)
        
        # Setup MongoDB connection
        if self._cache_settings.username and self._cache_settings.password:
            # Authenticated connection
            connection_string = f"mongodb://{self._cache_settings.username}:{self._cache_settings.password}@{self._cache_settings.endpoint}"
        else:
            # Unauthenticated connection
            connection_string = f"mongodb://{self._cache_settings.endpoint}"
            
        self._mongo_client = pymongo.MongoClient(connection_string)
        self._collection: Optional[Collection] = None
        super().__init__(settings=web_settings)

    def _get_collection(self) -> Collection:
        """Get the MongoDB collection, initializing it if necessary."""
        if self._collection is not None:
            return self._collection
        
        database = self._mongo_client[self._cache_settings.database]
        self._collection = database[self._cache_settings.collection]
        
        # Create an index on the id field for faster lookups
        self._collection.create_index("id", unique=True)
        
        return self._collection

    def get(
        self,
        url: str,
        data: Optional[Dict[str, Any]] = None,
        content_type: Optional[str] = None,
        url_extra: Optional[str] = None,
    ) -> Any:
        """GET (or POST) the content at the provided URL, using the cache if available."""
        cache_key = url.removeprefix("http://").removeprefix("https://")
        invalid_chars = ["?", "#", "(", ")", ":", "/"]
        invalid_subs = [urllib.parse.quote(c) for c in invalid_chars]

        for invalid in invalid_chars + invalid_subs:
            cache_key = cache_key.replace(invalid, "|")

        if data is not None:
            cache_key += f"&POST={self._invariant_hash(json.dumps(data))}"
        
        collection = self._get_collection()

        # Attempt to get the item from the cache
        item = collection.find_one({"id": cache_key})
        
        if item:
            logger.debug(f"{item['url']} served from {self._cache_settings.database}/{self._cache_settings.collection}.")
            code = item.get("status_code", 200)
        else:
            # If the item is not in the cache, fetch it from the web
            code, content = super()._get_content(url + (url_extra or ""), data)
            item = {"id": cache_key, "url": url, "status_code": code, "content": content}
            
            # Don't cache the response if it's a retryable/transient error or excluded code
            if code not in self._settings.retry_codes and code not in self._cache_settings.no_cache_codes:
                collection.insert_one(item)

        self._raise_for_status(code)
        return super()._transform_content(item["content"], content_type)

    def _invariant_hash(self, input: str) -> str:
        """Create a hash of the input string."""
        return hashlib.sha256(input.encode("utf-8")).hexdigest()