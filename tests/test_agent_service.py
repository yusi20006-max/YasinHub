from yasinhub.services.agent_service import AgentService


def main():
    service = AgentService()

    name = "test-agent"

    print("Health:")
    print(service.health(name))

    print("\nStatus:")
    print(service.status(name))

    print("\nRegister:")
    print(service.register(
        name,
        "YasinHub integration test agent"
    ))


if __name__ == "__main__":
    main()
