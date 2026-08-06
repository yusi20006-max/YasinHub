from yasinhub.services.ecosystem_service import EcosystemService


def main():

    service = EcosystemService()

    print("YasinHub Ecosystem Health:")
    print(service.health())


if __name__ == "__main__":
    main()
