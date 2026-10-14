from dataclasses import dataclass

import pytest
from flask import Flask

from mic_manager import MicConfig, MicError, MicInfo
from mic_provisioner import ProvisionState
from mic_routes import create_mic_blueprint


class FakeClient:
    alive = True
    calls = []

    def __init__(self, ip, **kwargs):
        self.ip = ip

    def get_status(self):
        if not FakeClient.alive:
            raise MicError("down")
        return {"streaming": True, "wifi_rssi": -60, "gain": 1.5, "hp_enable": False}

    def set_gain(self, gain):
        if not FakeClient.alive:
            raise MicError("down")
        if not 0.1 <= float(gain) <= 100:
            raise ValueError("range")
        FakeClient.calls.append(("gain", gain))

    def set_highpass(self, enabled):
        FakeClient.calls.append(("hp", enabled))

    def restart(self):
        if not FakeClient.alive:
            raise MicError("down")
        FakeClient.calls.append(("restart",))


@dataclass
class FakeService:
    config: MicConfig


class FakeProvisioner:
    def __init__(self):
        self.state = ProvisionState()
        self.started = 0

    def start(self):
        if self.state.running:
            return False
        self.started += 1
        self.state.running = True
        return True


@pytest.fixture
def setup(tmp_path):
    FakeClient.alive, FakeClient.calls = True, []
    cfg = MicConfig(str(tmp_path / "mic.json"))
    prov = FakeProvisioner()
    app = Flask(__name__)
    app.register_blueprint(create_mic_blueprint(
        FakeService(cfg), prov, remote_status=lambda: {"configured": True, "connected": True,
                                                       "last_handshake_seconds": 5},
        client_factory=FakeClient))
    return app.test_client(), cfg, prov


def test_status_unconfigured(setup):
    client, cfg, _ = setup
    assert client.get("/api/mic/status").get_json() == {"configured": False}


def test_status_reachable_and_unreachable(setup):
    client, cfg, _ = setup
    cfg.save(MicInfo("esp32mic-a", "10.0.0.5"))
    data = client.get("/api/mic/status").get_json()
    assert data["configured"] and data["reachable"] and data["connected"]
    assert data["hostname"] == "esp32mic-a" and data["rssi"] == -60
    FakeClient.alive = False
    data = client.get("/api/mic/status").get_json()
    assert data == {"configured": True, "reachable": False, "hostname": "esp32mic-a", "ip": "10.0.0.5"}


def test_settings(setup):
    client, cfg, _ = setup
    assert client.post("/api/mic/settings", json={"gain": 2}).status_code == 409
    cfg.save(MicInfo("esp32mic-a", "10.0.0.5"))
    assert client.post("/api/mic/settings", json={"gain": 2.5, "highpass_enabled": True}).status_code == 200
    assert FakeClient.calls == [("gain", 2.5), ("hp", True)]
    assert client.post("/api/mic/settings", json={"gain": 500}).status_code == 400
    assert client.post("/api/mic/settings", json={"gain": "loud"}).status_code == 400
    assert client.post("/api/mic/settings", json={}).status_code == 400
    assert client.post("/api/mic/settings", data="not json").status_code == 400
    FakeClient.alive = False
    assert client.post("/api/mic/settings", json={"gain": 2}).status_code == 502


def test_restart_and_forget(setup):
    client, cfg, _ = setup
    assert client.post("/api/mic/restart").status_code == 409
    cfg.save(MicInfo("esp32mic-a", "10.0.0.5"))
    assert client.post("/api/mic/restart").status_code == 200
    FakeClient.alive = False
    assert client.post("/api/mic/restart").status_code == 502
    assert client.post("/api/mic/forget").status_code == 200
    assert cfg.load() is None


def test_provision_start_status_and_double_tap(setup):
    client, _, prov = setup
    assert client.post("/api/mic/provision").status_code == 202
    assert client.post("/api/mic/provision").status_code == 409
    assert prov.started == 1
    assert client.get("/api/mic/provision/status").get_json()["running"] is True


def test_remote_help(setup):
    client, _, _ = setup
    assert client.get("/api/remote_help/status").get_json()["connected"] is True


def test_settings_rejected_by_mic_is_400(setup, monkeypatch):
    from mic_manager import MicRejected
    client, cfg, _ = setup
    cfg.save(MicInfo("esp32mic-a", "10.0.0.5"))

    def reject(self, enabled):
        raise MicRejected("invalid_value")
    monkeypatch.setattr(FakeClient, "set_highpass", reject)
    r = client.post("/api/mic/settings", json={"highpass_enabled": True})
    assert r.status_code == 400 and "rejected" in r.get_json()["message"].lower()
