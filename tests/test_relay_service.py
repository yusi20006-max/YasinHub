from yasinhub.services.relay_service import RelayService


def main():

    service = RelayService()

    print("Health:")
    print(service.health())

    print("\nConnect:")
    print(service.connect())

    print("\nEvent:")
    print(
        service.handle_event(
            "test_event",
            {
                "message": "hello"
            }
        )
    )


if __name__ == "__main__":
    main()
