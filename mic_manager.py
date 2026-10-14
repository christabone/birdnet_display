"""Find and talk to the outdoor ESP32 RTSP microphone."""
import json
import os
import time
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


def browse_mdns(timeout=5.0):
    """Return [(hostname, ip)] for esp32mic-* HTTP services on the LAN."""
    from zeroconf import ServiceBrowser, ServiceListener, Zeroconf

    found = {}

    class Listener(ServiceListener):
        def add_service(self, zc, type_, name):
            if not name.lower().startswith(MDNS_PREFIX):
                return
            info = zc.get_service_info(type_, name, timeout=2000)
            if info and info.parsed_addresses():
                found[name.split(".")[0]] = info.parsed_addresses()[0]

        def update_service(self, zc, type_, name):
            self.add_service(zc, type_, name)

        def remove_service(self, zc, type_, name):
            pass

    zc = Zeroconf()
    try:
        ServiceBrowser(zc, "_http._tcp.local.", Listener())
        time.sleep(timeout)
    finally:
        zc.close()
    return sorted(found.items())


def is_same_mic(status, hostname):
    """True unless the mic at this address reports a different hostname (older firmware may omit it)."""
    reported = status.get("mdns_hostname")
    return not reported or reported == hostname


def _responds(client_factory, ip, hostname=None):
    try:
        status = client_factory(ip, timeout=HTTP_TIMEOUT).get_status()
    except MicError:
        return False
    return hostname is None or is_same_mic(status, hostname)


def discover(saved=None, ignore=frozenset(), browse=browse_mdns, client_factory=MicClient):
    """Find the mic on the LAN. With `saved`, only that mic counts."""
    found = browse()
    if saved is not None:
        ips = [ip for host, ip in found if host == saved.hostname]
        if saved.ip not in ips:
            ips.append(saved.ip)
        for ip in ips:
            if _responds(client_factory, ip, saved.hostname):
                return MicInfo(saved.hostname, ip)
        return None
    for host, ip in found:
        if host not in ignore and _responds(client_factory, ip):
            return MicInfo(host, ip)
    return None
