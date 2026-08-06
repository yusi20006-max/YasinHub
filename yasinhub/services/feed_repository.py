from yasinhub.clients.yasinfeed_client import YasinFeedClient


class FeedRepository:

    def __init__(self):
        self.client = YasinFeedClient()

    def health(self):
        return self.client.health()

    def version(self):
        return self.client.version()

    def list_articles(self, page=1, limit=10):
        try:
            response = self.client.articles(page, limit)
            if response and isinstance(response, dict) and "data" in response:
                return response["data"]
            return []
        except Exception as e:
            print(f"Error in FeedRepository.list_articles: {e}")
            return []

    def get_article(self, article_id):
        try:
            return self.client.article(article_id)
        except Exception as e:
            print(f"Error in FeedRepository.get_article ({article_id}): {e}")
            return None
