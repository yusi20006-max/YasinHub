from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_api_exposes_program_status_data():
    source = (REPO_ROOT / "yasinhub/api/server.py").read_text(encoding="utf-8")
    assert '"projects": projects' in source
    assert '"name": r.name' in source
    assert '"status": r.health_state' in source
    assert '"last_run": r.last_run' in source


def test_pwa_overview_renders_program_names_and_active_state():
    source = (REPO_ROOT / "dashboard/js/views.js").read_text(encoding="utf-8")
    assert "const projects = Array.isArray(data && data.projects)" in source
    assert 'id="service-status-title">Yasin Programs' in source
    assert 'project.name || "Unnamed service"' in source
    assert "RUNNING / ACTIVE" in source
    assert 'class="service-status-list"' in source
