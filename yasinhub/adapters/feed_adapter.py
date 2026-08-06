from dataclasses import dataclass


@dataclass
class HubArticle:
    id: str
    title: str
    content: str
    published_at: str
    status: str


class FeedAdapter:

    def convert(self, article):
        return HubArticle(
            id=article.get("id"),
            title=article.get("title"),
            content=article.get("content"),
            published_at=article.get("published_at"),
            status=article.get("rewrite_status")
        )


    def convert_many(self, articles):
        return [
            self.convert(article)
            for article in articles
        ]
