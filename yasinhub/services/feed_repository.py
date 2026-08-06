from yasinhub.clients.yasinfeed_client import YasinFeedClient


class FeedRepository:

    def __init__(self):
        self.client = YasinFeedClient()

    def health(self):
        return self.client.health()

    def version(self):
        return self.client.version()

    def list_articles(self, page=1, limit=10):
        response = self.client.articles(page, limit)
        return response["data"]

    def get_article(self, article_id):
        return self.client.article(article_id)
