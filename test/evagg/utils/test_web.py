from unittest.mock import MagicMock, patch

import pytest
import requests
from pymongo.errors import DuplicateKeyError
from pytest import raises

from lib.evagg.utils import MongoDBCachingWebClient, RequestsWebContentClient


def test_settings():
    web_client = RequestsWebContentClient()
    web_client.update_settings(
        max_retries=1, retry_backoff=2, retry_codes=[500, 429], no_raise_codes=[422], content_type="json"
    )
    settings = web_client._settings.dict()
    assert settings["max_retries"] == 1
    assert settings["retry_backoff"] == 2
    assert settings["retry_codes"] == [500, 429]
    assert settings["no_raise_codes"] == [422]
    assert settings["content_type"] == "json"

    web_client.update_settings(max_retries=10)
    settings = web_client._settings.dict()
    assert settings["max_retries"] == 10
    assert settings["retry_backoff"] == 2

    with raises(ValueError):
        web_client.update_settings(invalid=1)


@patch("requests.sessions.Session.request")
def test_get_content_types(mock_request):
    mock_request.side_effect = [
        MagicMock(status_code=200, text="test"),
        MagicMock(status_code=200, text="<test>1</test>"),
        MagicMock(status_code=200, text='{"test": 1}'),
        MagicMock(status_code=200, text='{"test": 1}'),
    ]

    with raises(ValueError):
        RequestsWebContentClient(settings={"content_type": "binary"})

    web_client = RequestsWebContentClient()
    assert web_client.get("https://any.url/testing", content_type="text", url_extra="&extra") == "test"
    assert mock_request.call_args.args[1] == "https://any.url/testing&extra"
    assert web_client.get("https://any.url/testing", content_type="xml").tag == "test"  # type: ignore
    assert web_client.get("https://any.url/testing", content_type="json") == {"test": 1}
    with raises(ValueError):
        web_client.get("https://any.url/testing", content_type="invalid")


@patch("urllib3.connectionpool.HTTPConnectionPool._get_conn")
def test_retry_succeeded(mock_get_conn):
    mock_get_conn.return_value.getresponse.side_effect = [
        MagicMock(status=500, headers={}, iter_content=lambda _: [b""]),
        MagicMock(status=429, headers={}, iter_content=lambda _: [b""]),
        MagicMock(status=200, headers={}, iter_content=lambda _: [b""]),
    ]

    settings = {"max_retries": 2, "retry_backoff": 0, "retry_codes": [500, 429]}
    web_client = RequestsWebContentClient(settings)
    web_client.get("https://any.url/testing")

    assert mock_get_conn.return_value.request.call_args.args[0] == "GET"
    assert mock_get_conn.return_value.request.call_args.args[1] == "/testing"
    assert len(mock_get_conn.return_value.request.mock_calls) == 3


@patch("urllib3.connectionpool.HTTPConnectionPool._get_conn")
def test_retry_failed(mock_get_conn):
    mock_get_conn.return_value.getresponse.side_effect = [
        MagicMock(status=429, headers={}, iter_content=lambda _: [b""]),
        MagicMock(status=500, headers={}, iter_content=lambda _: [b""]),
    ]

    settings = {"max_retries": 1, "retry_backoff": 0, "retry_codes": [500, 429]}
    web_client = RequestsWebContentClient(settings)
    with raises(requests.exceptions.RetryError):
        web_client.get("https://any.url/testing")


@pytest.fixture
def mock_mongo_collection(json_load):
    class Collection:
        def __init__(self, cache):
            self.cache = {}
            for key, value in cache.items():
                self.cache[key] = value
            self.hits = []
            self.misses = []
            self.writes = []

        def find_one(self, query):
            item_id = query["id"]
            if item_id in self.cache:
                self.hits.append(item_id)
                return self.cache[item_id]
            self.misses.append(item_id)
            return None

        def insert_one(self, item):
            if item["id"] in self.cache:
                raise DuplicateKeyError("Duplicate key error")
            self.cache[item["id"]] = item
            self.writes.append(item)
            return MagicMock()

        def create_index(self, field, **kwargs):
            return True

    return Collection(json_load("cosmos_cache.json"))


@patch("pymongo.MongoClient")
def test_mongodb_cache_hit(mock_client, mock_mongo_collection):
    mock_client.return_value.__getitem__.return_value.__getitem__.return_value = mock_mongo_collection

    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=CPA6&sort=relevance&retmax=1&tool=biopython"  # noqa
    web_client = MongoDBCachingWebClient(cache_settings={"endpoint": "localhost:27017"})
    assert web_client.get(url, content_type="xml", url_extra="this doesn't matter").tag == "eSearchResult"
    assert web_client.get(url, content_type="xml").tag == "eSearchResult"

    url = "https://api.ncbi.nlm.nih.gov/datasets/v2alpha/gene/symbol/CPA6/taxon/Human"
    assert web_client.get(url, content_type="json", url_extra="extra")["reports"][0]["query"][0] == "CPA6"
    assert web_client.get(url, content_type="json")["reports"][0]["query"][0] == "CPA6"

    assert len(mock_mongo_collection.misses) == 0
    assert len(mock_mongo_collection.hits) == 4
    assert len(mock_mongo_collection.writes) == 0


@patch("requests.sessions.Session.request")
@patch("pymongo.MongoClient")
def test_mongodb_cache_miss(mock_client, mock_request, mock_mongo_collection):
    mock_client.return_value.__getitem__.return_value.__getitem__.return_value = mock_mongo_collection
    mock_request.side_effect = [
        MagicMock(status_code=200, text='<?xml version="1.0" encoding="UTF-8" ?><eSearchResult>GGG6</eSearchResult>'),
        MagicMock(status_code=200, text='{"reports": [{"query": ["GGG6"]}]}'),
        MagicMock(status_code=422, text='{"error": "invalid query, no throw"}'),
        MagicMock(status_code=500, text="throws, doesn't cache"),
        MagicMock(status_code=400, text="throws, caches"),
        MagicMock(status_code=400, text="throws, doesn't cache"),
        MagicMock(status_code=400, text="throws, doesn't cache"),
    ]

    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=GGG6&sort=relevance&retmax=1&tool=biopython"  # noqa
    web_client = MongoDBCachingWebClient(cache_settings={"endpoint": "localhost:27017"})
    web_client.update_settings(retry_codes=[500], no_raise_codes=[422])
    assert web_client.get(url, content_type="xml", url_extra="this doesn't matter").tag == "eSearchResult"
    assert web_client.get(url, content_type="xml").tag == "eSearchResult"

    url = "https://api.ncbi.nlm.nih.gov/datasets/v2alpha/gene/symbol/GGG6/taxon/Human"
    assert web_client.get(url, content_type="json", url_extra="extra")["reports"][0]["query"][0] == "GGG6"
    assert web_client.get(url, content_type="json")["reports"][0]["query"][0] == "GGG6"

    url = "https://testing.invalid/invalid/422"
    assert web_client.get(url, content_type="json", url_extra="extra")["error"] == "invalid query, no throw"
    assert web_client.get(url, content_type="json", url_extra="extra")["error"] == "invalid query, no throw"
    url = "https://testing.invalid/invalid/500"
    with raises(requests.exceptions.HTTPError):
        web_client.get(url, content_type="json")
    url = "https://testing.invalid/invalid/400-cache"
    with raises(requests.exceptions.HTTPError):
        web_client.get(url, content_type="json")
    with raises(requests.exceptions.HTTPError):
        web_client.get(url, content_type="json")
    url = "https://testing.invalid/invalid/400-no-cache"
    web_client._cache_settings.no_cache_codes = [400]
    with raises(requests.exceptions.HTTPError):
        web_client.get(url, content_type="json")
    with raises(requests.exceptions.HTTPError):
        web_client.get(url, content_type="json")

    assert len(mock_mongo_collection.misses) == 7
    assert len(mock_mongo_collection.writes) == 4
    assert len(mock_mongo_collection.hits) == 4


@patch("pymongo.MongoClient")
def test_mongodb_auth_connection(mock_client):
    MongoDBCachingWebClient(cache_settings={"endpoint": "localhost:27017", "username": "user", "password": "pass"})

    # Verify that the correct connection string was used
    mock_client.assert_called_once_with("mongodb://user:pass@localhost:27017")
