from yasinhub.services.core_service import CoreService


def main():
    service = CoreService()

    print("Health:")
    print(service.health())

    print("\nRuntime:")
    print(service.runtime_info())


if __name__ == "__main__":
    main()
