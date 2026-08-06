from yasinhub.services.feed_repository import FeedRepository
from yasinhub.adapters.feed_adapter import FeedAdapter


class FeedService:

    def __init__(self):
        self.repository = FeedRepository()
        self.adapter = FeedAdapter()

    def health(self):
        return self.repository.health()

    def version(self):
        return self.repository.version()

    def get_articles(self, page=1, limit=10):
        try:
            articles = self.repository.list_articles(
                page,
                limit
            )
            return self.adapter.convert_many(
                articles
            )
        except Exception as e:
            print(f"Error in FeedService.get_articles: {e}")
            return []

    def get_article(self, article_id):
        try:
            article = self.repository.get_article(
                article_id
            )
            if not article:
                return None
            return self.adapter.convert(
                article
            )
        except Exception as e:
            print(f"Error in FeedService.get_article ({article_id}): {e}")
            return None
