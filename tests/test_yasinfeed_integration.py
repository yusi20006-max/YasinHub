import json
from io import BytesIO
from unittest.mock import patch, MagicMock
import pytest
from yasinhub.clients.yasinfeed_client import YasinFeedClient


def mock_response(data, status_code=200):
    response = MagicMock()
    response.read.return_value = json.dumps(data).encode("utf-8")
    response.status = status_code
    return response


@patch("urllib.request.urlopen")
def test_yasinfeed_client_health_success(mock_urlopen):
    mock_data = {"service": "YasinFeed", "status": "healthy"}
    mock_urlopen.return_value.__enter__.return_value = mock_response(mock_data)

    client = YasinFeedClient()
    res = client.health()
    assert res["status"] == "healthy"
    assert res["service"] == "YasinFeed"


@patch("urllib.request.urlopen")
def test_yasinfeed_client_health_failure(mock_urlopen):
    mock_urlopen.side_effect = Exception("Connection refused")

    client = YasinFeedClient()
    res = client.health()
    assert res["status"] == "unhealthy"
    assert "خطا در ارتباط با کلاینت" in res["error"]


@patch("urllib.request.urlopen")
def test_yasinfeed_client_version_success(mock_urlopen):
    mock_urlopen.return_value.__enter__.return_value = mock_response("1.5.0")

    client = YasinFeedClient()
    assert client.version() == "1.5.0"


@patch("urllib.request.urlopen")
def test_yasinfeed_client_version_failure(mock_urlopen):
    mock_urlopen.side_effect = Exception("HTTP 500")

    client = YasinFeedClient()
    assert client.version() == "unknown"


@patch("urllib.request.urlopen")
def test_yasinfeed_client_routes_success(mock_urlopen):
    mock_routes = ["/api/health", "/api/version", "/api/articles"]
    mock_urlopen.return_value.__enter__.return_value = mock_response(mock_routes)

    client = YasinFeedClient()
    assert client.routes() == mock_routes


@patch("urllib.request.urlopen")
def test_yasinfeed_client_routes_failure(mock_urlopen):
    mock_urlopen.side_effect = Exception("Timeout")

    client = YasinFeedClient()
    assert client.routes() == []


@patch("urllib.request.urlopen")
def test_yasinfeed_client_stats_success(mock_urlopen):
    mock_stats = {"total": 100, "rewritten": 80}
    mock_urlopen.return_value.__enter__.return_value = mock_response(mock_stats)

    client = YasinFeedClient()
    assert client.stats() == mock_stats


@patch("urllib.request.urlopen")
def test_yasinfeed_client_stats_failure(mock_urlopen):
    mock_urlopen.side_effect = Exception("Error")

    client = YasinFeedClient()
    assert client.stats() == {}


@patch("urllib.request.urlopen")
def test_yasinfeed_client_articles_success(mock_urlopen):
    mock_articles = {"data": [{"id": "1", "title": "Article"}]}
    mock_urlopen.return_value.__enter__.return_value = mock_response(mock_articles)

    client = YasinFeedClient()
    assert client.articles(page=1, limit=5) == mock_articles


@patch("urllib.request.urlopen")
def test_yasinfeed_client_article_success(mock_urlopen):
    mock_article = {"id": "1", "title": "Article"}
    mock_urlopen.return_value.__enter__.return_value = mock_response(mock_article)

    client = YasinFeedClient()
    assert client.article("1") == mock_article
