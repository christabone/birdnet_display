"""Find and talk to the outdoor ESP32 RTSP microphone."""
import json
import os
from dataclasses import asdict, dataclass

import requests

MIC_CONFIG_FILE = "mic_config.json"
CSRF_HEADERS = {"X-ESP32MIC-CSRF": "1"}
HTTP_TIMEOUT = 3
MDNS_PREFIX = "esp32mic-"


@dataclass(frozen=True)
class MicInfo:
    hostname: str
    ip: str


class MicError(Exception):
    """The mic could not be reached or rejected a request."""


class MicConfig:
    """Remembers which mic this display uses (hostname + last known IP)."""

    def __init__(self, path=MIC_CONFIG_FILE):
        self.path = path

    def load(self):
        try:
            with open(self.path) as f:
                data = json.load(f)
            return MicInfo(hostname=str(data["hostname"]), ip=str(data["ip"]))
        except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError):
            return None

    def save(self, info):
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(asdict(info), f)
        os.replace(tmp, self.path)

    def forget(self):
        try:
            os.remove(self.path)
        except FileNotFoundError:
            pass


class MicClient:
    """Thin wrapper around the birdnetgo-esp32-rtsp-mic JSON API."""

    def __init__(self, ip, session=None, timeout=HTTP_TIMEOUT):
        self.base = f"http://{ip}"
        self.http = session or requests
        self.timeout = timeout

    def get_status(self):
        try:
            r = self.http.get(f"{self.base}/api/status", timeout=self.timeout)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            raise MicError(str(e)) from e

    def _post(self, path, data=None):
        try:
            r = self.http.post(f"{self.base}{path}", data=data,
                               headers=CSRF_HEADERS, timeout=self.timeout)
            r.raise_for_status()
        except requests.RequestException as e:
            raise MicError(str(e)) from e

    def set_gain(self, gain):
        gain = float(gain)
        if not 0.1 <= gain <= 100:
            raise ValueError("gain must be between 0.1 and 100")
        self._post("/api/set", {"key": "gain", "value": f"{gain:.2f}"})

    def set_highpass(self, enabled):
        self._post("/api/set", {"key": "hp_enable", "value": "on" if enabled else "off"})

    def restart(self):
        self._post("/api/action/reboot")


def summarize_status(raw):
    """Reduce the firmware's /api/status to what the touchscreen shows."""
    return {
        "reachable": True,
        "connected": raw.get("streaming") is True,
        "rssi": raw.get("wifi_rssi"),
        "temperature_c": raw.get("temperature_c"),
        "overheat": raw.get("overheat_latched") is True,
        "gain": raw.get("gain"),
        "highpass_enabled": raw.get("hp_enable") is True,
        "fw_version": raw.get("fw_version"),
    }
