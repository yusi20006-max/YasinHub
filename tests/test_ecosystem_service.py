from yasinhub.services.ecosystem_service import EcosystemService


def main():

    service = EcosystemService()

    print("Health:")
    print(service.health())

    print("\nSummary:")
    print(service.summary())


if __name__ == "__main__":
    main()
