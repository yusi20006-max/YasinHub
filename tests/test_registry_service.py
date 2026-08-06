from yasinhub.services.registry_service import RegistryService


def main():

    service = RegistryService()

    print("Register:")
    print(
        service.register_service(
            "YasinFeed",
            {
                "type": "news-engine",
                "version": "1.0"
            }
        )
    )

    print("\nServices:")
    print(service.list_services())

    print("\nGet:")
    print(service.get_service("YasinFeed"))


if __name__ == "__main__":
    main()
