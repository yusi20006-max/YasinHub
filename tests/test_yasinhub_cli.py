import subprocess
import sys
from unittest.mock import patch, MagicMock
from yasinhub.cli import main as cli_main
from yasinhub.registry import ProjectEntry


def test_yhub_launcher_execution():
    """Verify that the yhub launcher runs correctly as a subprocess."""
    result = subprocess.run(
        ["./yhub", "--help"],
        capture_output=True,
        text=True,
        check=True
    )
    assert "yasinhub" in result.stdout or "usage" in result.stdout


def test_cli_doctor_command(capsys):
    """Verify that yhub doctor subcommand executes and prints system diagnostics."""
    with patch("yasinhub.services.doctor_service.DoctorService.run") as mock_run:
        mock_run.return_value = {
            "doctor": "YasinHub Doctor",
            "python": {
                "version": "3.12.0",
                "platform": "Linux-test-mock",
                "status": "ok"
            },
            "ecosystem": {
                "feed": {"service": "YasinFeed", "status": "unhealthy", "error": "mocked error"},
                "core": {"status": "healthy", "connected": True, "version": "1.0.0"},
                "agent": {"name": "default", "status": "healthy"},
                "relay": {"service": "YasinHub Relay Service", "status": "unknown"},
                "registry": {"service": "YasinHub Registry Service", "status": "ok", "projects": 5}
            }
        }

        exit_code = cli_main(["doctor"])
        assert exit_code == 0
        captured = capsys.readouterr()

        assert "YasinHub Doctor" in captured.out or "بررسی سلامت و عیب‌یابی سیستم" in captured.out
        assert "YasinFeed" in captured.out
        assert "YasinCore" in captured.out
        assert "Registry" in captured.out


def test_cli_process_commands_progress_reporting(capsys):
    """Verify that start, stop, restart commands output clear step-by-step progress reports."""
    mock_project = ProjectEntry(
        name="mock_svc",
        process_pattern="mock_svc.py",
        description="A mocked service",
        start_command="python3 mock_svc.py"
    )

    with patch("yasinhub.registry.default_registry", return_value=[mock_project]), \
         patch("yasinhub.service_manager.start_service", return_value=True) as mock_start:

        exit_code = cli_main(["start", "mock_svc"])
        assert exit_code == 0
        captured = capsys.readouterr()

        # Check for progress indicators
        assert "آغاز فرآیند" in captured.out
        assert "1/1" in captured.out
        assert "mock_svc" in captured.out
        assert "با موفقیت پردازش شد" in captured.out
        mock_start.assert_called_once_with(mock_project)
