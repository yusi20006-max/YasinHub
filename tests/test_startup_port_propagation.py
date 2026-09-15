from pathlib import Path

from yasinhub import startup


class FakeProcess:
    pid = 43210

    def poll(self):
        return None


def test_start_hub_process_propagates_explicit_port(tmp_path, monkeypatch):
    captured = {}

    def fake_popen(argv, **kwargs):
        captured['argv'] = argv
        captured['env'] = kwargs['env']
        return FakeProcess()

    monkeypatch.delenv('YASINHUB_PORT', raising=False)
    monkeypatch.setattr(startup, 'save_pid', lambda *_: None)
    startup.start_hub_process(
        host='127.0.0.1',
        port=7123,
        logs_dir=tmp_path,
        popen_factory=fake_popen,
    )

    assert captured['argv'] == [startup.sys.executable, '-m', 'yasinhub.api.server']
    assert captured['env']['YASINHUB_PORT'] == '7123'


def test_start_hub_process_propagates_resolved_canonical_port(tmp_path, monkeypatch):
    captured = {}

    def fake_popen(argv, **kwargs):
        captured['env'] = kwargs['env']
        return FakeProcess()

    monkeypatch.delenv('YASINHUB_PORT', raising=False)
    monkeypatch.setattr(startup, 'port_for', lambda name: None)
    monkeypatch.setattr(startup, 'save_pid', lambda *_: None)
    startup.start_hub_process(logs_dir=tmp_path, popen_factory=fake_popen)

    assert captured['env']['YASINHUB_PORT'] == '7000'
