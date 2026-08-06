from unittest.mock import patch, MagicMock
import pytest
from yasinhub.services.feed_service import FeedService
from yasinhub.adapters.feed_adapter import HubArticle


def test_feed_service_health_healthy():
    with patch("yasinhub.services.feed_repository.FeedRepository.health") as mock_health:
        mock_health.return_value = {"service": "YasinFeed", "status": "healthy"}
        service = FeedService()
        res = service.health()
        assert res["status"] == "healthy"


def test_feed_service_health_unhealthy():
    with patch("yasinhub.services.feed_repository.FeedRepository.health") as mock_health:
        mock_health.return_value = {"service": "YasinFeed", "status": "unhealthy", "error": "Connection failed"}
        service = FeedService()
        res = service.health()
        assert res["status"] == "unhealthy"


def test_feed_service_version():
    with patch("yasinhub.services.feed_repository.FeedRepository.version") as mock_version:
        mock_version.return_value = "1.2.3"
        service = FeedService()
        assert service.version() == "1.2.3"


def test_feed_service_get_articles_success():
    mock_articles = [
        {
            "id": "1",
            "title": "Article 1",
            "content": "Content 1",
            "published_at": "2026-08-01",
            "rewrite_status": "done"
        }
    ]
    with patch("yasinhub.services.feed_repository.FeedRepository.list_articles") as mock_list:
        mock_list.return_value = mock_articles
        service = FeedService()
        articles = service.get_articles(page=1, limit=5)
        assert len(articles) == 1
        assert isinstance(articles[0], HubArticle)
        assert articles[0].id == "1"
        assert articles[0].title == "Article 1"
        assert articles[0].status == "done"


def test_feed_service_get_articles_failure():
    with patch("yasinhub.services.feed_repository.FeedRepository.list_articles", side_effect=Exception("Database error")):
        service = FeedService()
        articles = service.get_articles(page=1, limit=5)
        assert articles == []


def test_feed_service_get_article_success():
    mock_article = {
        "id": "42",
        "title": "Special Article",
        "content": "Special Content",
        "published_at": "2026-08-02",
        "rewrite_status": "pending"
    }
    with patch("yasinhub.services.feed_repository.FeedRepository.get_article") as mock_get:
        mock_get.return_value = mock_article
        service = FeedService()
        article = service.get_article("42")
        assert article is not None
        assert article.id == "42"
        assert article.title == "Special Article"
        assert article.status == "pending"


def test_feed_service_get_article_not_found():
    with patch("yasinhub.services.feed_repository.FeedRepository.get_article") as mock_get:
        mock_get.return_value = None
        service = FeedService()
        article = service.get_article("999")
        assert article is None


def test_feed_service_get_article_failure():
    with patch("yasinhub.services.feed_repository.FeedRepository.get_article", side_effect=Exception("Network error")):
        service = FeedService()
        article = service.get_article("42")
        assert article is None
