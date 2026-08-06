from yasinhub.services.feed_service import FeedService


def main():

    service = FeedService()

    print("Service Health:")
    print(service.health())

    print("\nArticles:")

    articles = service.get_articles(1,3)

    for article in articles:
        print(article)


if __name__ == "__main__":
    main()
