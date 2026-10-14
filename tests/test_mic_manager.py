import json

import pytest
import requests

from mic_manager import (
    CSRF_HEADERS, MicClient, MicConfig, MicError, MicInfo, summarize_status,
)


class FakeResponse:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeSession:
    def __init__(self, get_response=None, post_response=None, exc=None):
        self.get_response = get_response or FakeResponse(payload={})
        self.post_response = post_response or FakeResponse()
        self.exc = exc
        self.calls = []

    def get(self, url, timeout):
        self.calls.append(("GET", url, None, None, timeout))
        if self.exc:
            raise self.exc
        return self.get_response

    def post(self, url, data=None, headers=None, timeout=None):
        self.calls.append(("POST", url, data, headers, timeout))
        if self.exc:
            raise self.exc
        return self.post_response


def test_config_round_trip(tmp_path):
    cfg = MicConfig(str(tmp_path / "mic_config.json"))
    assert cfg.load() is None
    cfg.save(MicInfo(hostname="esp32mic-a1b2c3", ip="192.168.1.50"))
    assert cfg.load() == MicInfo(hostname="esp32mic-a1b2c3", ip="192.168.1.50")
    cfg.forget()
    assert cfg.load() is None
    cfg.forget()  # forgetting twice is fine


def test_config_ignores_corrupt_file(tmp_path):
    path = tmp_path / "mic_config.json"
    path.write_text("{not json")
    assert MicConfig(str(path)).load() is None
    path.write_text(json.dumps({"hostname": "x"}))
    assert MicConfig(str(path)).load() is None


def test_get_status_returns_json():
    session = FakeSession(get_response=FakeResponse(payload={"streaming": True}))
    assert MicClient("10.0.0.5", session=session).get_status() == {"streaming": True}
    assert session.calls[0][1] == "http://10.0.0.5/api/status"
    assert session.calls[0][4] == 3


@pytest.mark.parametrize("exc", [requests.ConnectTimeout("t"), requests.ConnectionError("c")])
def test_get_status_wraps_network_errors(exc):
    with pytest.raises(MicError):
        MicClient("10.0.0.5", session=FakeSession(exc=exc)).get_status()


def test_get_status_wraps_bad_json_and_http_errors():
    with pytest.raises(MicError):
        MicClient("10.0.0.5", session=FakeSession(get_response=FakeResponse(payload=None))).get_status()
    with pytest.raises(MicError):
        MicClient("10.0.0.5", session=FakeSession(get_response=FakeResponse(status=500, payload={}))).get_status()


def test_set_gain_posts_with_csrf_header():
    session = FakeSession()
    MicClient("10.0.0.5", session=session).set_gain(2.5)
    method, url, data, headers, _ = session.calls[0]
    assert (method, url) == ("POST", "http://10.0.0.5/api/set")
    assert data == {"key": "gain", "value": "2.50"}
    assert headers == CSRF_HEADERS == {"X-ESP32MIC-CSRF": "1"}


@pytest.mark.parametrize("bad", [0.0, 0.05, 100.5, -1])
def test_set_gain_rejects_out_of_range(bad):
    session = FakeSession()
    with pytest.raises(ValueError):
        MicClient("10.0.0.5", session=session).set_gain(bad)
    assert session.calls == []


def test_set_highpass_and_restart():
    session = FakeSession()
    client = MicClient("10.0.0.5", session=session)
    client.set_highpass(True)
    client.set_highpass(False)
    client.restart()
    assert session.calls[0][2] == {"key": "hp_enable", "value": "on"}
    assert session.calls[1][2] == {"key": "hp_enable", "value": "off"}
    assert session.calls[2][1] == "http://10.0.0.5/api/action/reboot"


def test_post_wraps_errors():
    with pytest.raises(MicError):
        MicClient("10.0.0.5", session=FakeSession(exc=requests.ConnectionError("x"))).restart()


def test_summarize_status():
    raw = {
        "streaming": True, "wifi_rssi": -61, "temperature_c": 41.5,
        "overheat_latched": False, "gain": 1.5, "hp_enable": True, "fw_version": "1.26",
    }
    assert summarize_status(raw) == {
        "reachable": True, "connected": True, "rssi": -61, "temperature_c": 41.5,
        "overheat": False, "gain": 1.5, "highpass_enabled": True, "fw_version": "1.26",
    }


def test_summarize_status_tolerates_missing_fields():
    s = summarize_status({})
    assert s["reachable"] is True and s["connected"] is False
    assert s["rssi"] is None and s["highpass_enabled"] is False
