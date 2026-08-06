from yasinhub.clients.yasinfeed_client import YasinFeedClient
from yasinhub.adapters.feed_adapter import FeedAdapter


def main():

    client = YasinFeedClient()

    print("Health:")
    print(client.health())

    print("\nVersion:")
    print(client.version())

    print("\nArticles:")

    response = client.articles(1, 3)

    adapter = FeedAdapter()

    articles = adapter.convert_many(
        response["data"]
    )

    for article in articles:
        print(article)


if __name__ == "__main__":
    main()
