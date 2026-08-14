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


def test_cli_feed_subcommands(capsys):
    """Verify that the new feed subcommand executes status, articles, and article actions correctly."""
    from yasinhub.adapters.feed_adapter import HubArticle

    mock_service_instance = MagicMock()
    mock_service_instance.health.return_value = {"service": "YasinFeed", "status": "healthy"}
    mock_service_instance.version.return_value = "1.9.9"
    mock_service_instance.repository.client.stats.return_value = {"total_items": 100}
    mock_service_instance.repository.client.routes.return_value = ["/api/health"]

    mock_service_instance.get_articles.return_value = [
        HubArticle(id="1", title="Article 1", content="Content 1", published_at="2026-08-01", status="done")
    ]
    mock_service_instance.get_article.return_value = HubArticle(
        id="42", title="Special Article", content="Special Content", published_at="2026-08-02", status="pending"
    )

    with patch("yasinhub.services.feed_service.FeedService", return_value=mock_service_instance):
        # 1. feed status
        exit_code = cli_main(["feed", "status"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "وضعیت سرویس فیدخوان یاسین YasinFeed" in captured.out
        assert "سالم (Healthy)" in captured.out
        assert "1.9.9" in captured.out
        assert "total_items: 100" in captured.out

        # 2. feed articles
        exit_code = cli_main(["feed", "articles", "--page", "1", "--limit", "5"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "لیست مقالات فیدخوان" in captured.out
        assert "Article 1" in captured.out

        # 3. feed article
        exit_code = cli_main(["feed", "article", "42"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Special Article" in captured.out
        assert "Special Content" in captured.out


def test_cli_press_subcommands(capsys):
    """Verify that the new press subcommand executes status, health, and rewrites actions correctly."""
    mock_service_instance = MagicMock()
    mock_service_instance.health.return_value = {"service": "YasinPress Service", "status": "healthy"}
    mock_service_instance.get_status.return_value = {"status": "active", "total_posts": 150}
    mock_service_instance.get_rewrites.return_value = [
        {"id": "1", "original_title": "Original Test", "rewritten_title": "Rewritten Test", "status": "completed"}
    ]

    with patch("yasinhub.services.press_service.PressService", return_value=mock_service_instance):
        # 1. press status
        exit_code = cli_main(["press", "status"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "وضعیت سرویس پرس YasinPress" in captured.out
        assert "وضعیت فعلی: active" in captured.out
        assert "total_posts: 150" in captured.out

        # 2. press health
        exit_code = cli_main(["press", "health"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "بررسی سلامت سرویس پرس YasinPress" in captured.out
        assert "وضعیت سلامت: healthy" in captured.out

        # 3. press rewrites
        exit_code = cli_main(["press", "rewrites", "--limit", "5"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "YasinPress-Rewrite" in captured.out
        assert "Original Test" in captured.out
        assert "Rewritten Test" in captured.out
