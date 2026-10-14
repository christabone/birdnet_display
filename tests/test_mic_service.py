from mic_manager import MicConfig, MicError, MicInfo
from mic_service import MicService


def factory(alive):
    class Client:
        def __init__(self, ip, **kwargs):
            self.ip = ip

        def get_status(self):
            if self.ip not in alive:
                raise MicError("down")
            return {"streaming": True, "wifi_rssi": -58}
    return Client


def make(tmp_path, saved, alive, discovered=None, birdnet=None):
    cfg = MicConfig(str(tmp_path / "mic.json"))
    if saved:
        cfg.save(saved)
    calls = {"discover": 0, "birdnet": []}

    def discover_fn(saved=None, **kw):
        calls["discover"] += 1
        return discovered

    def update(ip):
        calls["birdnet"].append(ip)
        if birdnet:
            raise birdnet

    svc = MicService(cfg, client_factory=factory(alive), discover_fn=discover_fn, update_birdnet=update)
    return svc, cfg, calls


def test_no_saved_mic_does_nothing(tmp_path):
    svc, cfg, calls = make(tmp_path, None, set())
    svc.refresh_once()
    assert calls == {"discover": 0, "birdnet": []}


def test_busy_skips(tmp_path):
    svc, cfg, calls = make(tmp_path, MicInfo("esp32mic-a", "10.0.0.5"), {"10.0.0.5"})
    svc.refresh_once(busy=lambda: True)
    assert calls["birdnet"] == []


def test_reachable_mic_keeps_birdnet_pointed(tmp_path):
    svc, cfg, calls = make(tmp_path, MicInfo("esp32mic-a", "10.0.0.5"), {"10.0.0.5"})
    svc.refresh_once()
    assert calls == {"discover": 0, "birdnet": ["10.0.0.5"]}


def test_ip_change_is_saved_and_pushed(tmp_path):
    svc, cfg, calls = make(tmp_path, MicInfo("esp32mic-a", "10.0.0.5"), set(),
                           discovered=MicInfo("esp32mic-a", "10.0.0.9"))
    svc.refresh_once()
    assert cfg.load() == MicInfo("esp32mic-a", "10.0.0.9")
    assert calls["birdnet"] == ["10.0.0.9"]


def test_mic_gone_changes_nothing(tmp_path):
    svc, cfg, calls = make(tmp_path, MicInfo("esp32mic-a", "10.0.0.5"), set(), discovered=None)
    svc.refresh_once()
    assert cfg.load() == MicInfo("esp32mic-a", "10.0.0.5")
    assert calls["birdnet"] == []


def test_birdnet_errors_are_swallowed(tmp_path):
    svc, cfg, calls = make(tmp_path, MicInfo("esp32mic-a", "10.0.0.5"), {"10.0.0.5"},
                           birdnet=PermissionError("config.yaml"))
    svc.refresh_once()  # must not raise
    assert calls["birdnet"] == ["10.0.0.5"]


def test_audio_status_shapes(tmp_path):
    (tmp_path / "x").mkdir()
    svc, _, _ = make(tmp_path, MicInfo("esp32mic-a", "10.0.0.5"), {"10.0.0.5"})
    assert svc.audio_status() == {"connected": True, "rssi": -58}
    svc_down, _, _ = make(tmp_path / "x", MicInfo("esp32mic-a", "10.0.0.5"), set())
    assert svc_down.audio_status() == {"connected": False, "rssi": 0}


def test_audio_status_without_mic(tmp_path):
    svc, _, _ = make(tmp_path, None, set())
    assert svc.audio_status() == {"connected": False, "rssi": 0}
