"""Security regression tests for service command execution."""

from unittest.mock import patch

from yasinhub.registry import ProjectEntry
from yasinhub.service_manager import start_service, stop_service


def test_start_service_does_not_use_shell(tmp_path):
    project = ProjectEntry(
        name="safe-start",
        path=str(tmp_path),
        start_command="python3 -c \"print('ok')\"",
    )

    with patch("yasinhub.service_manager.read_pid", return_value=None), patch(
        "yasinhub.service_manager.check_process"
    ) as check_process, patch("yasinhub.service_manager.save_pid"), patch(
        "yasinhub.service_manager.time.sleep"
    ), patch("yasinhub.service_manager.subprocess.Popen") as popen:
        check_process.return_value.running = False
        process = popen.return_value
        process.pid = 1234
        process.poll.return_value = None

        assert start_service(project, logs_dir=tmp_path / "logs") is True

        assert popen.call_args.kwargs["shell"] is False
        assert isinstance(popen.call_args.args[0], list)
        assert popen.call_args.args[0][:2] == ["python3", "-c"]


def test_stop_service_does_not_use_shell(tmp_path):
    project = ProjectEntry(
        name="safe-stop",
        stop_command="python3 -c \"print('stop')\"",
    )

    with patch("yasinhub.service_manager.read_pid", return_value=None), patch(
        "yasinhub.service_manager.subprocess.run"
    ) as run, patch("yasinhub.service_manager.check_process") as check_process:
        check_process.return_value.running = False

        assert stop_service(project) is True

        assert run.call_args.kwargs["shell"] is False
        assert run.call_args.args[0][:2] == ["python3", "-c"]


def test_shell_metacharacters_are_not_interpreted():
    project = ProjectEntry(
        name="metachar",
        stop_command="python3 -c \"print('ok')\"; touch SHOULD_NOT_EXIST",
    )

    with patch("yasinhub.service_manager.read_pid", return_value=None), patch(
        "yasinhub.service_manager.subprocess.run"
    ) as run, patch("yasinhub.service_manager.check_process") as check_process:
        check_process.return_value.running = False
        assert stop_service(project) is True

        argv = run.call_args.args[0]
        assert any(";" in arg for arg in argv)
        assert run.call_args.kwargs["shell"] is False
