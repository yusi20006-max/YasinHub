from yasinhub.registry import DEFAULT_PROJECTS


def test_yasinrelay_default_start_command_is_noninteractive() -> None:
    relay = next(project for project in DEFAULT_PROJECTS if project.name == "yasinrelay")

    assert relay.start_command == (
        ".venv/bin/yasinrelay-termux run --schedule --non-interactive"
    )
    assert "--non-interactive" in relay.start_command
    assert "--schedule" in relay.start_command


def test_yasinrelay_registry_uses_termux_launcher() -> None:
    relay = next(project for project in DEFAULT_PROJECTS if project.name == "yasinrelay")

    assert relay.path is not None
    assert relay.start_command.startswith(".venv/bin/yasinrelay-termux ")
