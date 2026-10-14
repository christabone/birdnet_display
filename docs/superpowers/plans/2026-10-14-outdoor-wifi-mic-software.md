# Outdoor Wi-Fi Mic Software Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the BirdNET Display find, set up ("Add microphone"), monitor, and adjust an outdoor ESP32 RTSP mic on the home Wi-Fi from its touchscreen, keep BirdNET-Go pointed at it, and ship pre-loaded WireGuard "remote help".

**Architecture:** Small focused Python modules beside the existing Flask app:
- `mic_manager` — mic identity store, HTTP client, mDNS discovery
- `birdnet_go_config` — RTSP URL in BirdNET-Go's `config.yaml`
- `mic_service` — background re-discovery
- `mic_provisioner` — Wi-Fi handoff job
- `remote_help` — WireGuard status
- `mic_routes` — Flask blueprint

`birdnet_display.py` only wires them together. The touchscreen gets a new `#micModal` in `static/index.html`. A bench script `setup_remote_help.sh` pre-loads WireGuard.

**Tech Stack:** Python 3.11+ (Raspberry Pi OS Bookworm), Flask, requests, `zeroconf`, `ruamel.yaml`, NetworkManager (`nmcli`), WireGuard (`wireguard-tools`), pytest, vanilla JS.

**Spec:** `docs/superpowers/specs/2026-10-14-outdoor-wifi-mic-design.md` (approved 2026-10-14). Parts and firmware facts: `docs/parts-list.md`, `docs/research/sourcing-notes.md`.

**Out of scope for this plan:** enclosure CAD. It gets its own plan after the Bud PN-1320-MB arrives and is measured.

## Global Constraints

- Parents never paste, type config, or use a phone. The only parent-facing steps: join Wi-Fi on the touchscreen, tap **Add microphone**.
- Mic firmware: birdnetgo-esp32-rtsp-mic **v1.26+**. Every POST to the mic sends header `X-ESP32MIC-CSRF: 1`.
- Mic setup network SSID: **`ESP32-RTSP-Mic-AP`**. Portal: `http://192.168.4.1/wifisave` with form fields `s` (SSID) and `p` (password). The portal times out after **180 s**, and then the mic restarts.
- Mic mDNS hostnames start with **`esp32mic-`**; HTTP service type `_http._tcp`, port 80. RTSP URL: `rtsp://<ip>:8554/audio1`.
- Mic gain accepted range: **0.1–100** (firmware). High-pass: `hp_enable` = `on`/`off`.
- BirdNET-Go config: **`~/birdnet-go-app/config/config.yaml`**, key `realtime.rtsp.streams` (list of `{name, url, type, transport}`). Its Docker container cannot resolve `.local`, so we write the **IP**. Restart with `sudo -n systemctl restart birdnet-go.service`.
- The Pi's Wi-Fi interface is **`wlan0`**. The app already relies on passwordless `sudo` (Raspberry Pi OS default user).
- Any provisioning failure after leaving home Wi-Fi **must reconnect home Wi-Fi before reporting the error**. A detached watchdog (180 s) is the backstop.
- WireGuard: `AllowedIPs` = Chris's VPN subnet only; `PersistentKeepalive = 25`; endpoint is Chris's DDNS name; re-resolve every 5 min. Private keys, Wi-Fi passwords, `wg0.conf`, and `mic_config.json` are **never committed** (the fork is public).
- All subprocess calls use argv lists (no `shell=True`) so SSIDs/passwords with spaces, quotes, `&`, or `:` are safe.
- Git: work in `/home/ctabone/programming/claude_code/analysis/personal/birdnet/birdnet_display` on branch `outdoor-wifi-mic`. Stage explicit paths only. Never use `--no-verify`. If a hook blocks, stop and ask Chris.

## Review Focus

1. **The display is on Ethernet, or Wi-Fi is disconnected, when "Add microphone" is tapped.** Expect a plain message ("The display needs to be connected to Wi-Fi first"), no network changes. Test in Task 5.
2. **The home Wi-Fi name or password contains spaces, quotes, `&`, `:` or backslashes, or the network is open (no password).** Expect it to be passed through verbatim (`nmcli -g` escapes undone) and the open network to send `p=""`. Tests in Tasks 5 and 1.
3. **A neighbor's or the spare `esp32mic-*` is already on the LAN during setup.** Expect the newly joined mic to be chosen (pre-setup snapshot is ignored), and a saved mic to be preferred afterward. Tests in Task 2.
4. **The mic is unplugged or out of range while the touchscreen polls.** Expect a short timeout (≤3 s), a "not responding" status, and no hang or crash. Tests in Tasks 1, 4 and 6.
5. **BirdNET-Go's `config.yaml` is missing, unwritable, or the restart fails.** Expect the mic to still be saved, the setup to report "will retry automatically", and the background monitor to retry. Tests in Tasks 3, 4 and 5.

---

## File Structure

| File | Responsibility |
|---|---|
| `mic_manager.py` (new) | `MicInfo`, `MicConfig` (JSON store), `MicClient` (mic HTTP API), `summarize_status`, `browse_mdns`, `discover` |
| `birdnet_go_config.py` (new) | `mic_rtsp_url`, `set_mic_stream`, `restart_birdnet_go`, `point_birdnet_go_at` |
| `mic_service.py` (new) | `MicService.refresh_once` + background thread |
| `mic_provisioner.py` (new) | `NetworkOps` (nmcli wrapper), `Provisioner` job, `ProvisionState` |
| `remote_help.py` (new) | `remote_help_status` from `wg show` |
| `mic_routes.py` (new) | `create_mic_blueprint(...)` — `/api/mic/*`, `/api/remote_help/status` |
| `birdnet_display.py` (modify) | wire objects, register blueprint, `/audio_status` uses saved mic, start monitor |
| `rtsp_monitor.py` (modify) | read mic IP from `mic_config.json` |
| `static/index.html` (modify) | Microphone button, `#micModal`, remote-help dot, tappable mic icon |
| `setup_remote_help.sh` (new) | bench-only WireGuard + SSH pre-load |
| `install.sh` (modify) | copy new files, mDNS deps, fan overlay prompt |
| `requirements.txt`, `requirements-dev.txt`, `.gitignore`, `README.md` (modify/new) | deps, ignores, docs |
| `tests/` (new) | pytest suite |

---

### Task 1: Test harness, mic identity store, and mic HTTP client

**Files:**
- Create: `mic_manager.py`, `tests/conftest.py`, `tests/test_mic_manager.py`, `requirements-dev.txt`
- Modify: `requirements.txt`, `.gitignore`

**Interfaces:**
- Produces:
  - `MicInfo(hostname: str, ip: str)` (dataclass)
  - `MicConfig(path: str = "mic_config.json")` with `.load() -> MicInfo | None`, `.save(info: MicInfo) -> None`, `.forget() -> None`
  - `MicError(Exception)`
  - `MicClient(ip: str, session=None, timeout: float = 3)` with:
    - `.get_status() -> dict`
    - `.set_gain(gain: float) -> None` (raises `ValueError` outside 0.1–100)
    - `.set_highpass(enabled: bool) -> None`
    - `.restart() -> None`
    - All failures raise `MicError`.
  - `summarize_status(raw: dict) -> dict` with keys `reachable, connected, rssi, temperature_c, overheat, gain, highpass_enabled, fw_version`
  - Constants `CSRF_HEADERS`, `MDNS_PREFIX = "esp32mic-"`
  - Deviation from spec §3: the spec listed `mac` in `mic_config.json`, but the firmware's `/api/status` does not expose a MAC. The mDNS hostname (`esp32mic-xxxxxx`, unique per device) is the identity.

- [ ] **Step 1: Set up the dev environment**

Append to `requirements.txt`:
```
zeroconf
ruamel.yaml
```
Create `requirements-dev.txt`:
```
pytest
```
Append to `.gitignore`:
```

# Local runtime state (never commit)
mic_config.json
pinned_species.json
venv/
.venv/
```
Create `tests/conftest.py`:
```python
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
```
Run:
```bash
cd /home/ctabone/programming/claude_code/analysis/personal/birdnet/birdnet_display
python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt -r requirements-dev.txt
```
Expected: installs without error.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_mic_manager.py`:
```python
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
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_mic_manager.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mic_manager'`.

- [ ] **Step 4: Implement `mic_manager.py`**

```python
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
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_mic_manager.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add mic_manager.py tests/conftest.py tests/test_mic_manager.py requirements.txt requirements-dev.txt .gitignore
git commit -m "Add mic identity store and mic HTTP client"
```

---

### Task 2: mDNS discovery

**Files:**
- Modify: `mic_manager.py` (append)
- Test: `tests/test_discovery.py`

**Interfaces:**
- Consumes: `MicInfo`, `MicClient`, `MicError`, `MDNS_PREFIX` (Task 1)
- Produces:
  - `browse_mdns(timeout: float = 5.0) -> list[tuple[str, str]]`: `(hostname, ip)` pairs for `esp32mic-*`
  - `discover(saved: MicInfo | None = None, ignore: frozenset = frozenset(), browse=browse_mdns, client_factory=MicClient) -> MicInfo | None`

Rules for `discover`:
- **With `saved`:** only that hostname counts. Try its mDNS IP(s), then `saved.ip`; return the first that answers `/api/status`.
- **Without `saved`:** return the first responding mic whose hostname is not in `ignore`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_discovery.py`:
```python
from mic_manager import MicError, MicInfo, discover


def make_factory(alive_ips):
    class Client:
        def __init__(self, ip, **kwargs):
            self.ip = ip

        def get_status(self):
            if self.ip not in alive_ips:
                raise MicError("down")
            return {"streaming": True}
    return Client


def test_first_add_picks_new_mic_and_ignores_known_ones():
    found = [("esp32mic-neighbor", "192.168.1.40"), ("esp32mic-new", "192.168.1.77")]
    result = discover(ignore=frozenset({"esp32mic-neighbor"}), browse=lambda: found,
                      client_factory=make_factory({"192.168.1.40", "192.168.1.77"}))
    assert result == MicInfo("esp32mic-new", "192.168.1.77")


def test_first_add_skips_unresponsive():
    found = [("esp32mic-a", "192.168.1.40"), ("esp32mic-b", "192.168.1.41")]
    result = discover(browse=lambda: found, client_factory=make_factory({"192.168.1.41"}))
    assert result == MicInfo("esp32mic-b", "192.168.1.41")


def test_saved_mic_found_at_new_ip():
    saved = MicInfo("esp32mic-ours", "192.168.1.50")
    found = [("esp32mic-spare", "192.168.1.60"), ("esp32mic-ours", "192.168.1.51")]
    result = discover(saved=saved, browse=lambda: found,
                      client_factory=make_factory({"192.168.1.51", "192.168.1.60"}))
    assert result == MicInfo("esp32mic-ours", "192.168.1.51")


def test_saved_mic_falls_back_to_last_ip_when_mdns_silent():
    saved = MicInfo("esp32mic-ours", "192.168.1.50")
    result = discover(saved=saved, browse=lambda: [],
                      client_factory=make_factory({"192.168.1.50"}))
    assert result == saved


def test_saved_mic_never_swaps_to_another_mic():
    saved = MicInfo("esp32mic-ours", "192.168.1.50")
    found = [("esp32mic-spare", "192.168.1.60")]
    assert discover(saved=saved, browse=lambda: found,
                    client_factory=make_factory({"192.168.1.60"})) is None


def test_nothing_found():
    assert discover(browse=lambda: [], client_factory=make_factory(set())) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_discovery.py -v`
Expected: FAIL with `ImportError: cannot import name 'discover'`.

- [ ] **Step 3: Implement (append to `mic_manager.py`)**

Add `import time` to the imports at the top, then append:
```python
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


def _responds(client_factory, ip):
    try:
        client_factory(ip, timeout=HTTP_TIMEOUT).get_status()
        return True
    except MicError:
        return False


def discover(saved=None, ignore=frozenset(), browse=browse_mdns, client_factory=MicClient):
    """Find the mic on the LAN. With `saved`, only that mic counts."""
    found = browse()
    if saved is not None:
        ips = [ip for host, ip in found if host == saved.hostname]
        if saved.ip not in ips:
            ips.append(saved.ip)
        for ip in ips:
            if _responds(client_factory, ip):
                return MicInfo(saved.hostname, ip)
        return None
    for host, ip in found:
        if host not in ignore and _responds(client_factory, ip):
            return MicInfo(host, ip)
    return None
```

- [ ] **Step 4: Run all tests**

Run: `.venv/bin/pytest -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add mic_manager.py tests/test_discovery.py
git commit -m "Add mDNS discovery for the outdoor mic"
```

---

### Task 3: Point BirdNET-Go at the mic

**Files:**
- Create: `birdnet_go_config.py`, `tests/test_birdnet_go_config.py`

**Interfaces:**
- Produces:
  - `DEFAULT_CONFIG_PATH = os.path.expanduser("~/birdnet-go-app/config/config.yaml")`
  - `STREAM_NAME = "Outdoor Mic"`
  - `mic_rtsp_url(ip: str) -> str`
  - `set_mic_stream(url: str, config_path: str = DEFAULT_CONFIG_PATH) -> bool`: True if the file changed. Raises `FileNotFoundError` or `PermissionError` as-is.
  - `restart_birdnet_go(run=subprocess.run) -> None`: raises `subprocess.CalledProcessError` on failure.
  - `point_birdnet_go_at(ip: str, config_path: str = DEFAULT_CONFIG_PATH, run=subprocess.run) -> bool`: restarts only when changed.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_birdnet_go_config.py`:
```python
import subprocess

import pytest

from birdnet_go_config import (
    STREAM_NAME, mic_rtsp_url, point_birdnet_go_at, set_mic_stream,
)

BASE = """\
# BirdNET-Go config
realtime:
  interval: 15          # keep me
  rtsp:
    streams: []           # Audio streams for analysis
"""

WITH_OTHER = """\
realtime:
  rtsp:
    streams:
      - name: Garage Cam
        url: rtsp://192.168.1.9/stream
        type: rtsp
        transport: tcp
"""


def write(tmp_path, text):
    p = tmp_path / "config.yaml"
    p.write_text(text)
    return str(p)


def test_url_format():
    assert mic_rtsp_url("192.168.1.50") == "rtsp://192.168.1.50:8554/audio1"


def test_adds_stream_and_keeps_comments(tmp_path):
    path = write(tmp_path, BASE)
    assert set_mic_stream("rtsp://192.168.1.50:8554/audio1", path) is True
    text = open(path).read()
    assert "rtsp://192.168.1.50:8554/audio1" in text
    assert STREAM_NAME in text
    assert "# keep me" in text and "# BirdNET-Go config" in text


def test_unchanged_returns_false(tmp_path):
    path = write(tmp_path, BASE)
    set_mic_stream("rtsp://192.168.1.50:8554/audio1", path)
    assert set_mic_stream("rtsp://192.168.1.50:8554/audio1", path) is False


def test_updates_ip_in_place_and_keeps_other_streams(tmp_path):
    path = write(tmp_path, WITH_OTHER)
    set_mic_stream("rtsp://192.168.1.50:8554/audio1", path)
    assert set_mic_stream("rtsp://192.168.1.51:8554/audio1", path) is True
    text = open(path).read()
    assert "Garage Cam" in text
    assert "192.168.1.51" in text and "192.168.1.50" not in text
    assert text.count(STREAM_NAME) == 1


def test_missing_config_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        set_mic_stream("rtsp://x", str(tmp_path / "nope.yaml"))


def test_point_restarts_only_when_changed(tmp_path):
    path = write(tmp_path, BASE)
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    assert point_birdnet_go_at("192.168.1.50", path, run=run) is True
    assert calls == [["sudo", "-n", "systemctl", "restart", "birdnet-go.service"]]
    assert point_birdnet_go_at("192.168.1.50", path, run=run) is False
    assert len(calls) == 1


def test_restart_failure_raises(tmp_path):
    path = write(tmp_path, BASE)

    def run(cmd, **kwargs):
        raise subprocess.CalledProcessError(1, cmd)

    with pytest.raises(subprocess.CalledProcessError):
        point_birdnet_go_at("192.168.1.50", path, run=run)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_birdnet_go_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'birdnet_go_config'`.

- [ ] **Step 3: Implement `birdnet_go_config.py`**

```python
"""Keep BirdNET-Go's RTSP input pointed at the outdoor mic."""
import os
import subprocess

from ruamel.yaml import YAML

DEFAULT_CONFIG_PATH = os.path.expanduser("~/birdnet-go-app/config/config.yaml")
STREAM_NAME = "Outdoor Mic"


def mic_rtsp_url(ip):
    return f"rtsp://{ip}:8554/audio1"


def set_mic_stream(url, config_path=DEFAULT_CONFIG_PATH):
    """Add or update the 'Outdoor Mic' stream. Returns True if the file changed."""
    yaml = YAML()  # round-trip mode keeps comments and ordering
    with open(config_path) as f:
        data = yaml.load(f) or {}
    realtime = data.setdefault("realtime", {})
    rtsp = realtime.setdefault("rtsp", {})
    streams = rtsp.get("streams") or []
    for stream in streams:
        if stream.get("name") == STREAM_NAME:
            if stream.get("url") == url:
                return False
            stream["url"] = url
            break
    else:
        streams.append({"name": STREAM_NAME, "url": url, "type": "rtsp", "transport": "tcp"})
    rtsp["streams"] = streams
    tmp = config_path + ".tmp"
    with open(tmp, "w") as f:
        yaml.dump(data, f)
    os.replace(tmp, config_path)
    return True


def restart_birdnet_go(run=subprocess.run):
    run(["sudo", "-n", "systemctl", "restart", "birdnet-go.service"],
        check=True, capture_output=True, text=True, timeout=90)


def point_birdnet_go_at(ip, config_path=DEFAULT_CONFIG_PATH, run=subprocess.run):
    """Make BirdNET-Go listen to the mic at `ip`. Returns True if it was changed."""
    changed = set_mic_stream(mic_rtsp_url(ip), config_path)
    if changed:
        restart_birdnet_go(run=run)
    return changed
```

- [ ] **Step 4: Run all tests**

Run: `.venv/bin/pytest -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add birdnet_go_config.py tests/test_birdnet_go_config.py
git commit -m "Point BirdNET-Go's RTSP stream at the outdoor mic"
```

---

### Task 4: Background mic monitor, `/audio_status`, and `rtsp_monitor.py`

**Files:**
- Create: `mic_service.py`, `tests/test_mic_service.py`
- Modify: `birdnet_display.py` (imports near the top; `/audio_status` at about lines 439–452; `__main__` block at the end), `rtsp_monitor.py` (constants at lines 10–13)

**Interfaces:**
- Consumes: `MicConfig`, `MicClient`, `MicError`, `discover` (Tasks 1–2); `point_birdnet_go_at` (Task 3)
- Produces:
  - `MicService(config: MicConfig, client_factory=MicClient, discover_fn=discover, update_birdnet=point_birdnet_go_at)`
  - `.refresh_once(busy=lambda: False) -> None`
  - `.start_background(busy, interval: float = 60) -> threading.Thread`
  - `.audio_status() -> dict` with keys `{"connected": bool, "rssi": int}` (the existing route's shape)

Rules for `refresh_once`:
- Do nothing if `busy()` is true or no mic is saved.
- If the saved IP doesn't answer, run `discover(saved=...)`. If the mic answers at a new IP, save it.
- Always call `update_birdnet(current_ip)` (idempotent) and swallow and log its errors, so a failed BirdNET-Go update is retried next cycle.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_mic_service.py`:
```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_mic_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mic_service'`.

- [ ] **Step 3: Implement `mic_service.py`**

```python
"""Keep track of the outdoor mic: re-find it if its IP changes, keep BirdNET-Go pointed at it."""
import threading
import time

from birdnet_go_config import point_birdnet_go_at
from mic_manager import MicClient, MicError, discover

STATUS_TIMEOUT = 2


class MicService:
    def __init__(self, config, client_factory=MicClient, discover_fn=discover,
                 update_birdnet=point_birdnet_go_at):
        self.config = config
        self.client_factory = client_factory
        self.discover_fn = discover_fn
        self.update_birdnet = update_birdnet

    def _status(self, ip):
        return self.client_factory(ip, timeout=STATUS_TIMEOUT).get_status()

    def refresh_once(self, busy=lambda: False):
        if busy():
            return
        saved = self.config.load()
        if saved is None:
            return
        current = saved
        try:
            self._status(saved.ip)
        except MicError:
            current = self.discover_fn(saved=saved)
            if current is None:
                return
            if current != saved:
                self.config.save(current)
                print(f"[INFO] Mic moved to {current.ip}")
        try:
            self.update_birdnet(current.ip)
        except Exception as e:
            print(f"[WARN] Could not update BirdNET-Go for mic {current.ip}: {e}")

    def start_background(self, busy, interval=60):
        def loop():
            while True:
                try:
                    self.refresh_once(busy=busy)
                except Exception as e:
                    print(f"[WARN] Mic monitor error: {e}")
                time.sleep(interval)
        thread = threading.Thread(target=loop, name="mic-monitor", daemon=True)
        thread.start()
        return thread

    def audio_status(self):
        mic = self.config.load()
        if mic is None:
            return {"connected": False, "rssi": 0}
        try:
            raw = self._status(mic.ip)
        except MicError:
            return {"connected": False, "rssi": 0}
        return {"connected": raw.get("streaming") is True, "rssi": raw.get("wifi_rssi", 0)}
```

- [ ] **Step 4: Run all tests**

Run: `.venv/bin/pytest -v`
Expected: all PASS.

- [ ] **Step 5: Wire into `birdnet_display.py`**

After the existing line `from cache_builder import CACHE_DIRECTORY, SPECIES_FILE, load_species_from_file`, add:
```python
from mic_manager import MicConfig
from mic_service import MicService
```
After `DETECTION_CACHE = { "id": None, "raw_data": [] }`, add:
```python

# --- Outdoor Mic ---
MIC_CONFIG = MicConfig(os.path.join(os.path.dirname(os.path.abspath(__file__)), "mic_config.json"))
MIC_SERVICE = MicService(MIC_CONFIG)
```
Replace the whole `audio_status` function (the `@app.route('/audio_status')` block that hardcodes `10.42.0.50`) with:
```python
@app.route('/audio_status')
def audio_status():
    return jsonify(MIC_SERVICE.audio_status())
```
In `__main__`, before `print(f"Starting Flask server on http://0.0.0.0:{SERVER_PORT}")`, add:
```python
    MIC_SERVICE.start_background(busy=lambda: False)
```
(Task 6 replaces `lambda: False` with the provisioner's running flag.)

- [ ] **Step 6: Fix `rtsp_monitor.py`**

Replace the configuration block:
```python
# Configuration
STATUS_URL = "http://10.42.0.50/api/status"
REBOOT_URL = "http://10.42.0.50/api/action/reboot"
TIMEOUT = 10  # seconds
```
with:
```python
import json
import os

# Configuration: the mic's address comes from the display's saved mic (mic_config.json).
MIC_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mic_config.json")
TIMEOUT = 10  # seconds


def _mic_ip():
    with open(MIC_CONFIG_PATH) as f:
        return json.load(f)["ip"]


try:
    _IP = _mic_ip()
except (OSError, ValueError, KeyError):
    print(f"No mic configured ({MIC_CONFIG_PATH}); nothing to check.")
    sys.exit(0)

STATUS_URL = f"http://{_IP}/api/status"
REBOOT_URL = f"http://{_IP}/api/action/reboot"
```
Also add the `X-ESP32MIC-CSRF` header to the reboot POST. Change `requests.post(REBOOT_URL, timeout=TIMEOUT)` to:
```python
            requests.post(REBOOT_URL, headers={"X-ESP32MIC-CSRF": "1"}, timeout=TIMEOUT)
```

- [ ] **Step 7: Smoke-check imports**

Run: `.venv/bin/python -c "import ast,sys; [ast.parse(open(f).read()) for f in ('birdnet_display.py','rtsp_monitor.py')]; print('ok')"`
Expected: `ok`.

Then run: `.venv/bin/python -c "import birdnet_display; print(birdnet_display.MIC_SERVICE)"`
Expected: prints a `MicService` object. If `cache_builder` imports fail locally, `pip install -r requirements.txt` first.

- [ ] **Step 8: Commit**

```bash
git add mic_service.py tests/test_mic_service.py birdnet_display.py rtsp_monitor.py
git commit -m "Track the mic by saved identity instead of a hardcoded IP"
```

---

### Task 5: "Add microphone" provisioner

**Files:**
- Create: `mic_provisioner.py`, `tests/test_mic_provisioner.py`

**Interfaces:**
- Consumes: `MicConfig`, `MicInfo`, `discover`, `browse_mdns` (Tasks 1–2); `point_birdnet_go_at` (Task 3)
- Produces:
  - `SETUP_SSID = "ESP32-RTSP-Mic-AP"`, `SETUP_CON_NAME = "birdnet-mic-setup"`
  - `NetworkOps(run=subprocess.run, popen=subprocess.Popen)` with:
    - `.active_connection() -> str | None`
    - `.wifi_credentials(con: str) -> tuple[str, str]`
    - `.sees_network(ssid: str) -> bool`
    - `.join_open(ssid: str, con_name: str) -> None`
    - `.up(con: str) -> None`
    - `.delete(con: str) -> None`
    - `.arm_watchdog(con: str, seconds: int) -> Popen`
  - `ProvisionState` dataclass: `running: bool, step: str | None, message: str, done: bool, error: str | None, mic: dict | None`
  - `Provisioner(net, config, discover_fn=discover, snapshot_fn=..., update_birdnet=point_birdnet_go_at, http=requests, sleep=time.sleep)` with:
    - `.start() -> bool` (False if already running)
    - `.run_sync() -> None` (used by tests and by `start`'s thread)
    - `.state -> ProvisionState`
    - `.running -> bool`

**Flow:**
1. `find_setup_network`: wait up to 12 × 10 s for `ESP32-RTSP-Mic-AP`.
2. `read_home_wifi`: read the `wlan0` connection and its SSID/PSK. Fail if there is none.
3. Snapshot the mic hostnames already on the LAN.
4. Arm the watchdog.
5. `join_setup_network`.
6. `send_wifi_details`: POST `s`, `p`, 2 attempts. Failure is soft; we still look for the mic.
7. `return_home`: always runs; 3 attempts; delete the setup profile.
8. Kill the watchdog only if back home.
9. `find_mic`: up to 9 attempts, 10 s apart, with `ignore=snapshot`.
10. Save the mic.
11. `connect_birdnet`: an error here is a warning only, since the monitor retries.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_mic_provisioner.py`:
```python
import subprocess

import pytest
import requests

from mic_manager import MicConfig, MicInfo
from mic_provisioner import SETUP_CON_NAME, SETUP_SSID, NetworkOps, Provisioner


class FakeNet:
    def __init__(self, sees=True, home="Home WiFi", creds=("Mom's Wi-Fi & \"stuff\"", "p@ss:w\\rd"),
                 join_error=None, up_fail_times=0):
        self.sees = sees
        self.home = home
        self.creds = creds
        self.join_error = join_error
        self.up_fail_times = up_fail_times
        self.log = []
        self.watchdog = FakeProc()

    def sees_network(self, ssid):
        self.log.append(("scan", ssid))
        return self.sees

    def active_connection(self):
        return self.home

    def wifi_credentials(self, con):
        self.log.append(("creds", con))
        return self.creds

    def arm_watchdog(self, con, seconds):
        self.log.append(("watchdog", con, seconds))
        return self.watchdog

    def join_open(self, ssid, con_name):
        self.log.append(("join", ssid, con_name))
        if self.join_error:
            raise self.join_error

    def up(self, con):
        self.log.append(("up", con))
        if self.up_fail_times > 0:
            self.up_fail_times -= 1
            raise RuntimeError("no carrier")

    def delete(self, con):
        self.log.append(("delete", con))


class FakeProc:
    def __init__(self):
        self.killed = False

    def kill(self):
        self.killed = True


class FakeHttp:
    def __init__(self, fail_times=0):
        self.fail_times = fail_times
        self.posts = []

    def post(self, url, data=None, timeout=None):
        self.posts.append((url, data))
        if self.fail_times > 0:
            self.fail_times -= 1
            raise requests.ConnectionError("AP dropped")

        class R:
            status_code = 200

            def raise_for_status(self):
                pass
        return R()


def make(tmp_path, net=None, http=None, found=MicInfo("esp32mic-new", "192.168.1.77"),
         known=frozenset({"esp32mic-neighbor"}), birdnet_error=None):
    cfg = MicConfig(str(tmp_path / "mic.json"))
    seen = {}

    def discover_fn(saved=None, ignore=frozenset(), **kw):
        seen["ignore"] = ignore
        return found

    def update_birdnet(ip):
        seen["birdnet"] = ip
        if birdnet_error:
            raise birdnet_error

    p = Provisioner(net or FakeNet(), cfg, discover_fn=discover_fn, snapshot_fn=lambda: known,
                    update_birdnet=update_birdnet, http=http or FakeHttp(), sleep=lambda s: None)
    return p, cfg, seen


def test_happy_path(tmp_path):
    net, http = FakeNet(), FakeHttp()
    p, cfg, seen = make(tmp_path, net=net, http=http)
    p.run_sync()
    assert p.state.done and p.state.error is None and not p.state.running
    assert http.posts == [("http://192.168.4.1/wifisave", {"s": "Mom's Wi-Fi & \"stuff\"", "p": "p@ss:w\\rd"})]
    assert ("join", SETUP_SSID, SETUP_CON_NAME) in net.log
    assert net.log.index(("up", "Home WiFi")) > net.log.index(("join", SETUP_SSID, SETUP_CON_NAME))
    assert ("delete", SETUP_CON_NAME) in net.log
    assert net.watchdog.killed
    assert seen["ignore"] == frozenset({"esp32mic-neighbor"})
    assert cfg.load() == MicInfo("esp32mic-new", "192.168.1.77")
    assert seen["birdnet"] == "192.168.1.77"


def test_not_on_wifi_fails_without_touching_network(tmp_path):
    net = FakeNet(home=None)
    p, cfg, _ = make(tmp_path, net=net)
    p.run_sync()
    assert "connected to Wi-Fi" in p.state.error
    assert not any(e[0] in ("join", "watchdog", "up") for e in net.log)


def test_setup_network_never_appears(tmp_path):
    net = FakeNet(sees=False)
    p, _, _ = make(tmp_path, net=net)
    p.run_sync()
    assert "unplug" in p.state.error.lower()
    assert sum(1 for e in net.log if e[0] == "scan") == 12
    assert not any(e[0] == "join" for e in net.log)


def test_join_failure_still_returns_home_first(tmp_path):
    net = FakeNet(join_error=RuntimeError("secrets required"))
    p, cfg, _ = make(tmp_path, net=net)
    p.run_sync()
    assert p.state.error
    assert ("up", "Home WiFi") in net.log
    assert net.watchdog.killed
    assert cfg.load() is None


def test_post_dropped_but_mic_joined_counts_as_success(tmp_path):
    p, cfg, _ = make(tmp_path, http=FakeHttp(fail_times=2))
    p.run_sync()
    assert p.state.done and p.state.error is None
    assert cfg.load() is not None


def test_post_failed_and_mic_missing_reports_send_error(tmp_path):
    p, cfg, _ = make(tmp_path, http=FakeHttp(fail_times=2), found=None)
    p.run_sync()
    assert "didn't accept" in p.state.error


def test_return_home_retries_then_succeeds(tmp_path):
    net = FakeNet(up_fail_times=2)
    p, _, _ = make(tmp_path, net=net)
    p.run_sync()
    assert p.state.done
    assert sum(1 for e in net.log if e == ("up", "Home WiFi")) == 3
    assert net.watchdog.killed


def test_return_home_fails_leaves_watchdog_armed(tmp_path):
    net = FakeNet(up_fail_times=99)
    p, _, _ = make(tmp_path, net=net)
    p.run_sync()
    assert "reconnect" in p.state.error
    assert not net.watchdog.killed


def test_mic_not_found_after_handoff(tmp_path):
    p, cfg, _ = make(tmp_path, found=None)
    p.run_sync()
    assert "couldn't find" in p.state.error.lower()
    assert cfg.load() is None


def test_birdnet_failure_is_a_warning(tmp_path):
    p, cfg, _ = make(tmp_path, birdnet_error=PermissionError("config.yaml"))
    p.run_sync()
    assert p.state.done and p.state.error is None
    assert "retry" in p.state.message.lower()
    assert cfg.load() is not None


def test_start_refuses_second_run(tmp_path):
    p, _, _ = make(tmp_path)
    p.state.running = True
    assert p.start() is False


# --- NetworkOps (nmcli argv building + unescaping) ---

def fake_run(outputs):
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        key = tuple(cmd[1:4])
        out, code = outputs.get(key, ("", 0))
        return subprocess.CompletedProcess(cmd, code, out, "err")
    return run, calls


def test_wifi_credentials_unescapes_nmcli_terse_output():
    run, calls = fake_run({
        ("-s", "-g", "802-11-wireless.ssid"): ("Mom\\:s Net\n", 0),
        ("-s", "-g", "802-11-wireless-security.psk"): ("a\\\\b\\:c\n", 0),
    })
    assert NetworkOps(run=run).wifi_credentials("Home") == ("Mom:s Net", "a\\b:c")
    assert all(isinstance(c, list) for c in calls)


def test_wifi_credentials_open_network_has_empty_psk():
    run, _ = fake_run({
        ("-s", "-g", "802-11-wireless.ssid"): ("Open Net\n", 0),
        ("-s", "-g", "802-11-wireless-security.psk"): ("", 10),
    })
    assert NetworkOps(run=run).wifi_credentials("Home") == ("Open Net", "")


def test_active_connection_none_when_disconnected():
    run, _ = fake_run({("-g", "GENERAL.CONNECTION", "dev"): ("\n", 0)})
    assert NetworkOps(run=run).active_connection() is None


def test_join_open_creates_non_autoconnect_profile():
    run, calls = fake_run({})
    NetworkOps(run=run).join_open(SETUP_SSID, SETUP_CON_NAME)
    add = next(c for c in calls if c[1:3] == ["con", "add"])
    assert "connection.autoconnect" in add and add[add.index("connection.autoconnect") + 1] == "no"
    assert ["nmcli", "con", "up", SETUP_CON_NAME] in calls


def test_watchdog_passes_connection_as_argument_not_shell_text():
    started = {}

    def popen(cmd, **kwargs):
        started["cmd"] = cmd
        started["kwargs"] = kwargs
        return FakeProc()

    NetworkOps(popen=popen).arm_watchdog("Mom's \"Net\"; rm -rf /", 180)
    cmd = started["cmd"]
    assert cmd[:2] == ["sh", "-c"]
    assert cmd[-1] == "Mom's \"Net\"; rm -rf /"
    assert started["kwargs"]["start_new_session"] is True
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_mic_provisioner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mic_provisioner'`.

- [ ] **Step 3: Implement `mic_provisioner.py`**

```python
"""'Add microphone': hand the display's home Wi-Fi to the mic's setup network."""
import subprocess
import threading
import time
from dataclasses import dataclass

import requests

from birdnet_go_config import point_birdnet_go_at
from mic_manager import browse_mdns, discover

IFACE = "wlan0"
SETUP_SSID = "ESP32-RTSP-Mic-AP"
SETUP_CON_NAME = "birdnet-mic-setup"
SETUP_PORTAL = "http://192.168.4.1/wifisave"
WATCHDOG_SECONDS = 180
SCAN_ATTEMPTS, SCAN_INTERVAL = 12, 10
HOME_ATTEMPTS, HOME_INTERVAL = 3, 5
FIND_ATTEMPTS, FIND_INTERVAL = 9, 10


def _unescape(value):
    """Undo nmcli terse-mode escaping of ':' and '\\'."""
    out, i = [], 0
    while i < len(value):
        if value[i] == "\\" and i + 1 < len(value):
            out.append(value[i + 1])
            i += 2
        else:
            out.append(value[i])
            i += 1
    return "".join(out)


class NetworkOps:
    """NetworkManager calls used by the provisioner. argv lists only, never a shell string."""

    def __init__(self, run=subprocess.run, popen=subprocess.Popen):
        self.run = run
        self.popen = popen

    def _nmcli(self, *args, timeout=30, check=True):
        r = self.run(["nmcli", *args], capture_output=True, text=True, timeout=timeout)
        if check and r.returncode != 0:
            raise RuntimeError((r.stderr or r.stdout or "nmcli failed").strip())
        return r

    def active_connection(self):
        out = self._nmcli("-g", "GENERAL.CONNECTION", "dev", "show", IFACE, check=False).stdout
        name = _unescape(out.strip())
        return name or None

    def _field(self, con, field):
        r = self._nmcli("-s", "-g", field, "connection", "show", con, check=False)
        return _unescape(r.stdout.rstrip("\n")) if r.returncode == 0 else ""

    def wifi_credentials(self, con):
        return self._field(con, "802-11-wireless.ssid"), self._field(con, "802-11-wireless-security.psk")

    def sees_network(self, ssid):
        self._nmcli("dev", "wifi", "rescan", "ifname", IFACE, check=False)
        out = self._nmcli("-t", "-f", "SSID", "dev", "wifi", "list", "ifname", IFACE, check=False).stdout
        return any(_unescape(line) == ssid for line in out.splitlines())

    def join_open(self, ssid, con_name):
        self._nmcli("con", "delete", con_name, check=False)
        self._nmcli("con", "add", "type", "wifi", "ifname", IFACE, "con-name", con_name,
                    "ssid", ssid, "connection.autoconnect", "no")
        self._nmcli("con", "up", con_name, timeout=45)

    def up(self, con):
        self._nmcli("con", "up", con, timeout=45)

    def delete(self, con):
        self._nmcli("con", "delete", con, check=False)

    def arm_watchdog(self, con, seconds):
        """Detached backstop: reconnect home Wi-Fi even if this process dies."""
        return self.popen(
            ["sh", "-c", 'sleep "$1"; nmcli con up "$2"', "mic-setup-watchdog", str(seconds), con],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
        )


@dataclass
class ProvisionState:
    running: bool = False
    step: str = None
    message: str = ""
    done: bool = False
    error: str = None
    mic: dict = None


class ProvisionError(Exception):
    pass


class Provisioner:
    def __init__(self, net, config, discover_fn=discover,
                 snapshot_fn=lambda: frozenset(h for h, _ in browse_mdns()),
                 update_birdnet=point_birdnet_go_at, http=requests, sleep=time.sleep):
        self.net = net
        self.config = config
        self.discover_fn = discover_fn
        self.snapshot_fn = snapshot_fn
        self.update_birdnet = update_birdnet
        self.http = http
        self.sleep = sleep
        self.state = ProvisionState()
        self._lock = threading.Lock()

    @property
    def running(self):
        return self.state.running

    def start(self):
        with self._lock:
            if self.state.running:
                return False
            self.state = ProvisionState(running=True, step="find_setup_network",
                                        message="Looking for the microphone…")
        threading.Thread(target=self.run_sync, name="mic-provision", daemon=True).start()
        return True

    def _step(self, step, message):
        self.state.step, self.state.message = step, message

    def _fail(self, message):
        self.state.error, self.state.message, self.state.running = message, message, False

    def run_sync(self):
        self.state.running = True
        try:
            self._run()
        except Exception as e:  # never leave the UI spinning
            print(f"[ERROR] Mic setup crashed: {e}")
            self._fail("Something went wrong setting up the microphone. Please try again.")

    def _run(self):
        try:
            home, ssid, psk, known = self._prepare()
        except ProvisionError as e:
            return self._fail(str(e))

        watchdog = self.net.arm_watchdog(home, WATCHDOG_SECONDS)
        join_error, sent = None, False
        try:
            self._step("join_setup_network",
                       "Connecting to the microphone — the display will be offline for about a minute.")
            self.net.join_open(SETUP_SSID, SETUP_CON_NAME)
            self._step("send_wifi_details", "Giving the microphone your Wi-Fi details…")
            sent = self._send_credentials(ssid, psk)
        except Exception as e:
            join_error = e
            print(f"[WARN] Could not join mic setup network: {e}")

        restored = self._return_home(home)
        if restored:
            watchdog.kill()
        if join_error is not None:
            return self._fail("Couldn't connect to the microphone. Unplug it for 5 seconds, plug it back in, and try again.")
        if not restored:
            return self._fail("The display couldn't reconnect to Wi-Fi. It will try again by itself in a few minutes.")

        self._step("find_mic", "Waiting for the microphone to join your Wi-Fi…")
        mic = self._find_mic(known)
        if mic is None:
            if not sent:
                return self._fail("The microphone didn't accept the Wi-Fi details. Unplug it for 5 seconds and try again.")
            return self._fail("Couldn't find the microphone on your Wi-Fi. Check it's plugged in, then try again.")

        self.config.save(mic)
        self.state.mic = {"hostname": mic.hostname, "ip": mic.ip}
        self._step("connect_birdnet", "Connecting BirdNET to the microphone…")
        message = "Microphone added! Birds will start showing up soon."
        try:
            self.update_birdnet(mic.ip)
        except Exception as e:
            print(f"[WARN] BirdNET-Go update failed: {e}")
            message = "Microphone added. BirdNET is still being connected — it will retry automatically."
        self.state.message, self.state.done, self.state.running = message, True, False

    def _prepare(self):
        self._step("find_setup_network", "Looking for the microphone…")
        if not self._wait_for_setup_network():
            raise ProvisionError("Couldn't find the microphone. Unplug its power for 5 seconds, plug it back in, then try again.")
        self._step("read_home_wifi", "Reading your Wi-Fi details…")
        home = self.net.active_connection()
        if not home:
            raise ProvisionError("The display needs to be connected to Wi-Fi first.")
        ssid, psk = self.net.wifi_credentials(home)
        if not ssid:
            raise ProvisionError("The display needs to be connected to Wi-Fi first.")
        known = frozenset(self.snapshot_fn())
        return home, ssid, psk, known

    def _wait_for_setup_network(self):
        for attempt in range(SCAN_ATTEMPTS):
            if self.net.sees_network(SETUP_SSID):
                return True
            if attempt < SCAN_ATTEMPTS - 1:
                self.sleep(SCAN_INTERVAL)
        return False

    def _send_credentials(self, ssid, psk):
        for _ in range(2):
            try:
                r = self.http.post(SETUP_PORTAL, data={"s": ssid, "p": psk}, timeout=10)
                r.raise_for_status()
                return True
            except requests.RequestException as e:
                print(f"[WARN] Sending Wi-Fi details failed: {e}")
                self.sleep(2)
        return False

    def _return_home(self, home):
        self._step("return_home", "Reconnecting the display to your Wi-Fi…")
        restored = False
        for attempt in range(HOME_ATTEMPTS):
            try:
                self.net.up(home)
                restored = True
                break
            except Exception as e:
                print(f"[WARN] Reconnect attempt {attempt + 1} failed: {e}")
                self.sleep(HOME_INTERVAL)
        self.net.delete(SETUP_CON_NAME)
        return restored

    def _find_mic(self, known):
        for attempt in range(FIND_ATTEMPTS):
            mic = self.discover_fn(ignore=known)
            if mic is not None:
                return mic
            if attempt < FIND_ATTEMPTS - 1:
                self.sleep(FIND_INTERVAL)
        return None
```

- [ ] **Step 4: Run all tests**

Run: `.venv/bin/pytest -v`
Expected: all PASS. If `test_wifi_credentials_unescapes_nmcli_terse_output` fails, check that `fake_run` keys on `cmd[1:4]` = `("-s", "-g", "<field>")`.

- [ ] **Step 5: Commit**

```bash
git add mic_provisioner.py tests/test_mic_provisioner.py
git commit -m "Add 'Add microphone' Wi-Fi handoff with guaranteed return to home Wi-Fi"
```

---

### Task 6: Flask API (`/api/mic/*`, `/api/remote_help/status`)

**Files:**
- Create: `remote_help.py`, `mic_routes.py`, `tests/test_remote_help.py`, `tests/test_mic_routes.py`
- Modify: `birdnet_display.py` (register the blueprint; pass the provisioner's busy flag to the monitor)

**Interfaces:**
- Consumes: `MicService` (Task 4); `Provisioner`, `NetworkOps` (Task 5); `MicClient`, `MicError`, `summarize_status` (Task 1)
- Produces:
  - `remote_help_status(run=subprocess.run, now=time.time, iface="wg0", fresh_seconds=180) -> dict` with keys `configured, connected, last_handshake_seconds`
  - `create_mic_blueprint(service, provisioner, remote_status=remote_help_status, client_factory=MicClient) -> Blueprint`

| Route | Method | Success | Errors |
|---|---|---|---|
| `/api/mic/status` | GET | `{"configured": false}` or `{"configured": true, "hostname", "ip", ...summarize_status}` or `{"configured": true, "reachable": false, "hostname", "ip"}` | — |
| `/api/mic/settings` | POST JSON `{"gain": float}` and/or `{"highpass_enabled": bool}` | `{"status": "ok"}` | 400 bad input, 409 no mic, 502 mic unreachable |
| `/api/mic/restart` | POST | `{"status": "ok"}` | 409, 502 |
| `/api/mic/forget` | POST | `{"status": "ok"}` | — |
| `/api/mic/provision` | POST | 202 `{"status": "started"}` | 409 `{"status": "already_running"}` |
| `/api/mic/provision/status` | GET | `asdict(ProvisionState)` | — |
| `/api/remote_help/status` | GET | `remote_help_status()` | — |

- [ ] **Step 1: Write the failing tests**

Create `tests/test_remote_help.py`:
```python
import subprocess

from remote_help import remote_help_status


def runner(stdout="", code=0, exc=None):
    def run(cmd, **kwargs):
        assert cmd == ["sudo", "-n", "wg", "show", "wg0", "latest-handshakes"]
        if exc:
            raise exc
        return subprocess.CompletedProcess(cmd, code, stdout, "")
    return run


def test_fresh_handshake_is_connected():
    s = remote_help_status(run=runner("PUBKEY=\t1000\n"), now=lambda: 1060)
    assert s == {"configured": True, "connected": True, "last_handshake_seconds": 60}


def test_stale_handshake_is_not_connected():
    s = remote_help_status(run=runner("PUBKEY=\t1000\n"), now=lambda: 2000)
    assert s["configured"] and not s["connected"] and s["last_handshake_seconds"] == 1000


def test_never_handshaked():
    s = remote_help_status(run=runner("PUBKEY=\t0\n"), now=lambda: 2000)
    assert s == {"configured": True, "connected": False, "last_handshake_seconds": None}


def test_not_configured_or_missing_tools():
    assert remote_help_status(run=runner(code=1))["configured"] is False
    assert remote_help_status(run=runner(exc=FileNotFoundError("wg")))["configured"] is False
    assert remote_help_status(run=runner(exc=subprocess.TimeoutExpired("wg", 5)))["configured"] is False
```

Create `tests/test_mic_routes.py`:
```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_remote_help.py tests/test_mic_routes.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `remote_help.py`**

```python
"""Is the WireGuard 'remote help' tunnel to Chris's home up?"""
import subprocess
import time


def remote_help_status(run=subprocess.run, now=time.time, iface="wg0", fresh_seconds=180):
    try:
        r = run(["sudo", "-n", "wg", "show", iface, "latest-handshakes"],
                capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return {"configured": False, "connected": False, "last_handshake_seconds": None}
    if r.returncode != 0:
        return {"configured": False, "connected": False, "last_handshake_seconds": None}
    latest = 0
    for line in r.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) == 2 and parts[1].strip().isdigit():
            latest = max(latest, int(parts[1]))
    if latest == 0:
        return {"configured": True, "connected": False, "last_handshake_seconds": None}
    age = max(0, int(now() - latest))
    return {"configured": True, "connected": age < fresh_seconds, "last_handshake_seconds": age}
```

- [ ] **Step 4: Implement `mic_routes.py`**

```python
"""Touchscreen API for the outdoor mic and remote help."""
from dataclasses import asdict

from flask import Blueprint, jsonify, request

from mic_manager import MicClient, MicError, summarize_status
from remote_help import remote_help_status


def create_mic_blueprint(service, provisioner, remote_status=remote_help_status,
                         client_factory=MicClient):
    bp = Blueprint("mic", __name__)

    def saved_mic():
        return service.config.load()

    @bp.get("/api/mic/status")
    def mic_status():
        mic = saved_mic()
        if mic is None:
            return jsonify({"configured": False})
        base = {"configured": True, "hostname": mic.hostname, "ip": mic.ip}
        try:
            raw = client_factory(mic.ip, timeout=2).get_status()
        except MicError:
            return jsonify({**base, "reachable": False})
        return jsonify({**base, **summarize_status(raw)})

    @bp.post("/api/mic/settings")
    def mic_settings():
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or not ({"gain", "highpass_enabled"} & body.keys()):
            return jsonify({"status": "error", "message": "Nothing to change"}), 400
        if "highpass_enabled" in body and not isinstance(body["highpass_enabled"], bool):
            return jsonify({"status": "error", "message": "highpass_enabled must be true/false"}), 400
        if "gain" in body:
            try:
                float(body["gain"])
            except (TypeError, ValueError):
                return jsonify({"status": "error", "message": "gain must be a number"}), 400
        mic = saved_mic()
        if mic is None:
            return jsonify({"status": "error", "message": "No microphone set up"}), 409
        client = client_factory(mic.ip)
        try:
            if "gain" in body:
                client.set_gain(float(body["gain"]))
            if "highpass_enabled" in body:
                client.set_highpass(body["highpass_enabled"])
        except ValueError as e:
            return jsonify({"status": "error", "message": str(e)}), 400
        except MicError:
            return jsonify({"status": "error", "message": "Microphone not responding"}), 502
        return jsonify({"status": "ok"})

    @bp.post("/api/mic/restart")
    def mic_restart():
        mic = saved_mic()
        if mic is None:
            return jsonify({"status": "error", "message": "No microphone set up"}), 409
        try:
            client_factory(mic.ip).restart()
        except MicError:
            return jsonify({"status": "error", "message": "Microphone not responding"}), 502
        return jsonify({"status": "ok"})

    @bp.post("/api/mic/forget")
    def mic_forget():
        service.config.forget()
        return jsonify({"status": "ok"})

    @bp.post("/api/mic/provision")
    def mic_provision():
        if not provisioner.start():
            return jsonify({"status": "already_running"}), 409
        return jsonify({"status": "started"}), 202

    @bp.get("/api/mic/provision/status")
    def mic_provision_status():
        return jsonify(asdict(provisioner.state))

    @bp.get("/api/remote_help/status")
    def remote_help():
        return jsonify(remote_status())

    return bp
```

- [ ] **Step 5: Run all tests**

Run: `.venv/bin/pytest -v`
Expected: all PASS.

- [ ] **Step 6: Wire into `birdnet_display.py`**

Extend the Task 4 imports:
```python
from mic_manager import MicConfig
from mic_provisioner import NetworkOps, Provisioner
from mic_routes import create_mic_blueprint
from mic_service import MicService
```
After `MIC_SERVICE = MicService(MIC_CONFIG)` add:
```python
PROVISIONER = Provisioner(NetworkOps(), MIC_CONFIG)
app.register_blueprint(create_mic_blueprint(MIC_SERVICE, PROVISIONER))
```
In `__main__`, change `MIC_SERVICE.start_background(busy=lambda: False)` to:
```python
    MIC_SERVICE.start_background(busy=lambda: PROVISIONER.running)
```

- [ ] **Step 7: Smoke test the wired app**

Run:
```bash
.venv/bin/python - <<'EOF'
import birdnet_display as b
c = b.app.test_client()
print(c.get("/api/mic/status").get_json())
print(c.get("/api/mic/provision/status").get_json())
print(c.get("/audio_status").get_json())
EOF
```
Expected: `{'configured': False}`, a state dict with `running: False`, `{'connected': False, 'rssi': 0}`.

- [ ] **Step 8: Commit**

```bash
git add remote_help.py mic_routes.py tests/test_remote_help.py tests/test_mic_routes.py birdnet_display.py
git commit -m "Add mic and remote-help API routes"
```

---

### Task 7: Touchscreen UI — Microphone modal and remote-help dot

**Files:**
- Modify: `static/index.html`
- Test: `tests/test_index_html.py`

**Interfaces:**
- Consumes: routes from Task 6; existing JS helpers `getSignalStrength(rssi)` (returns `{bars, class}`) and `showConfirmModal(message, action)`; existing CSS classes `settings-btn`, `settings-group`, `system-buttons`, `system-btn`, `restart-btn`, `power-btn`, `wifi-status`
- Produces: DOM ids `micModal`, `mic-settings-btn-modal`, `mic-status-block`, `mic-controls`, `mic-gain-slider`, `mic-gain-value`, `mic-highpass-toggle`, `mic-restart-btn`, `mic-forget-btn`, `mic-add-btn`, `mic-provision-progress`, `remote-help-dot`

- [ ] **Step 1: Write the failing structural test**

Create `tests/test_index_html.py`:
```python
import os
import re

HTML = open(os.path.join(os.path.dirname(__file__), "..", "static", "index.html")).read()

IDS = ["micModal", "mic-settings-btn-modal", "mic-status-block", "mic-controls", "mic-gain-slider",
       "mic-gain-value", "mic-highpass-toggle", "mic-restart-btn", "mic-forget-btn", "mic-add-btn",
       "mic-provision-progress", "remote-help-dot"]


def test_mic_ui_elements_exist_once():
    for element_id in IDS:
        assert len(re.findall(rf'id="{element_id}"', HTML)) == 1, element_id


def test_ui_calls_new_api():
    for path in ["/api/mic/status", "/api/mic/settings", "/api/mic/restart", "/api/mic/forget",
                 "/api/mic/provision", "/api/mic/provision/status", "/api/remote_help/status"]:
        assert f"'{path}'" in HTML, path


def test_no_hardcoded_mic_ip():
    assert "10.42.0.50" not in HTML
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/pytest tests/test_index_html.py -v`
Expected: FAIL on `micModal`.

- [ ] **Step 3: Add CSS**

After the line `#pinnedModal { z-index: 1350; }` add:
```css
        #micModal { z-index: 1320; }
        #micModal .modal-content { min-width: 600px; max-width: 90vw; color: #111; }
        .mic-status-block { font-size: 1.15em; font-weight: 600; padding: 12px; border-radius: 8px; background: #f1f5f9; }
        .mic-toggle { display: flex; align-items: center; gap: 12px; font-size: 1.1em; }
        .mic-toggle input { width: 28px; height: 28px; }
        #mic-gain-slider { width: 100%; height: 36px; }
        .remote-help-row { display: flex; align-items: center; gap: 8px; font-size: 0.95em; color: #475569; margin-top: 15px; }
        .remote-help-dot { width: 12px; height: 12px; border-radius: 50%; background: #cbd5e1; display: inline-block; }
        .remote-help-dot.on { background: #16a34a; }
        #mic-status-icon { cursor: pointer; }
```

- [ ] **Step 4: Add the Microphone button and remote-help row to the Settings modal**

In `#settingsModal`, after the `pinned-settings-btn-modal` settings-group `</div>`, add:
```html
            <div class="settings-group">
                <button id="mic-settings-btn-modal" class="settings-btn" style="width: 100%;">Microphone</button>
            </div>
```
After the closing `</div>` of `.system-buttons` (still inside `.modal-content`), add:
```html
            <div class="remote-help-row"><span id="remote-help-dot" class="remote-help-dot"></span> Remote help</div>
```

- [ ] **Step 5: Add the modal markup**

Immediately before `<div id="confirmModal" class="modal-overlay">`, add:
```html
    <div id="micModal" class="modal-overlay">
        <div class="modal-content">
            <h2>Microphone</h2>
            <div id="mic-status-block" class="settings-group mic-status-block">Checking…</div>
            <div id="mic-controls" style="display: none;">
                <div class="settings-group">
                    <label for="mic-gain-slider">Sensitivity: <span id="mic-gain-value">–</span></label>
                    <input type="range" id="mic-gain-slider" min="0.5" max="10" step="0.5" value="1.5">
                </div>
                <div class="settings-group">
                    <label class="mic-toggle"><input type="checkbox" id="mic-highpass-toggle"> Reduce wind &amp; traffic noise</label>
                </div>
                <div class="system-buttons">
                    <button id="mic-restart-btn" class="system-btn restart-btn">Restart mic</button>
                    <button id="mic-forget-btn" class="system-btn power-btn">Remove mic</button>
                </div>
            </div>
            <div class="settings-group" style="margin-top: 20px;">
                <button id="mic-add-btn" class="settings-btn" style="width: 100%;">Add microphone</button>
                <div id="mic-provision-progress" class="wifi-status" style="margin-top: 12px;"></div>
            </div>
        </div>
    </div>

```

- [ ] **Step 6: Add the JS**

Immediately before the line `// ========================================` that precedes `// PINNED SPECIES MANAGEMENT`, add:
```javascript
            // ========================================
            // MICROPHONE MODAL
            // ========================================
            const micModal = document.getElementById('micModal');
            const micStatusBlock = document.getElementById('mic-status-block');
            const micControls = document.getElementById('mic-controls');
            const micGainSlider = document.getElementById('mic-gain-slider');
            const micGainValue = document.getElementById('mic-gain-value');
            const micHighpassToggle = document.getElementById('mic-highpass-toggle');
            const micAddBtn = document.getElementById('mic-add-btn');
            const micProvisionProgress = document.getElementById('mic-provision-progress');
            let micProvisionTimer = null;

            function hideMicModal() { micModal.style.display = 'none'; }
            async function showMicModal(e) {
                e.stopPropagation();
                e.preventDefault();
                micModal.style.display = 'flex';
                await loadMicStatus();
            }
            ['mic-settings-btn-modal', 'mic-status-icon'].forEach(id => {
                const el = document.getElementById(id);
                el.addEventListener('click', showMicModal);
                el.addEventListener('touchend', showMicModal);
            });
            micModal.addEventListener('click', e => {
                if (!e.target.closest('.modal-content')) hideMicModal();
            });

            async function loadMicStatus() {
                try {
                    const response = await fetch('/api/mic/status');
                    renderMicStatus(await response.json());
                } catch (error) {
                    micStatusBlock.textContent = 'Could not check the microphone.';
                    micControls.style.display = 'none';
                }
            }

            function renderMicStatus(data) {
                if (!data.configured) {
                    micStatusBlock.textContent = 'No microphone set up yet.';
                    micControls.style.display = 'none';
                    micAddBtn.textContent = 'Add microphone';
                    return;
                }
                micAddBtn.textContent = 'Set up microphone again';
                if (!data.reachable) {
                    micStatusBlock.textContent = 'Microphone not responding. Check that it is plugged in.';
                    micControls.style.display = 'none';
                    return;
                }
                const signal = getSignalStrength(data.rssi);
                const temp = data.temperature_c == null ? '' : ` · ${Math.round(data.temperature_c)}°C`;
                const state = data.overheat ? 'Too hot — paused' : (data.connected ? 'Listening' : 'Connected, not streaming');
                micStatusBlock.textContent = `${state} · Signal ${signal.bars}/4${temp}`;
                micControls.style.display = 'block';
                if (data.gain != null) {
                    micGainSlider.value = data.gain;
                    micGainValue.textContent = Number(data.gain).toFixed(1);
                }
                micHighpassToggle.checked = !!data.highpass_enabled;
            }

            async function postMicSettings(body) {
                try {
                    const response = await fetch('/api/mic/settings', {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(body)
                    });
                    if (!response.ok) showMicProgress('The microphone did not respond. Try again in a moment.', true);
                } catch (error) {
                    showMicProgress('The microphone did not respond. Try again in a moment.', true);
                }
            }
            micGainSlider.addEventListener('input', e => { micGainValue.textContent = Number(e.target.value).toFixed(1); });
            micGainSlider.addEventListener('change', e => postMicSettings({ gain: Number(e.target.value) }));
            micHighpassToggle.addEventListener('change', e => postMicSettings({ highpass_enabled: e.target.checked }));

            document.getElementById('mic-restart-btn').addEventListener('click', () => {
                showConfirmModal('Restart the microphone? It takes about 30 seconds.', async () => {
                    await fetch('/api/mic/restart', { method: 'POST' });
                    micStatusBlock.textContent = 'Restarting…';
                    setTimeout(loadMicStatus, 30000);
                });
            });
            document.getElementById('mic-forget-btn').addEventListener('click', () => {
                showConfirmModal('Remove this microphone from the display?', async () => {
                    await fetch('/api/mic/forget', { method: 'POST' });
                    await loadMicStatus();
                });
            });

            function showMicProgress(message, isError) {
                micProvisionProgress.textContent = message;
                micProvisionProgress.className = 'wifi-status ' + (isError ? 'error' : 'success');
                micProvisionProgress.style.display = 'block';
            }

            function stopProvisionPolling() {
                clearInterval(micProvisionTimer);
                micProvisionTimer = null;
                micAddBtn.disabled = false;
            }

            function pollProvision() {
                clearInterval(micProvisionTimer);
                micAddBtn.disabled = true;
                micProvisionTimer = setInterval(async () => {
                    let state;
                    try {
                        state = await (await fetch('/api/mic/provision/status')).json();
                    } catch (error) {
                        return; // the page is served locally, so this is rare; just keep polling
                    }
                    if (state.error) {
                        stopProvisionPolling();
                        showMicProgress(state.error, true);
                        micAddBtn.textContent = 'Try again';
                    } else if (state.done) {
                        stopProvisionPolling();
                        showMicProgress(state.message, false);
                        await loadMicStatus();
                    } else {
                        showMicProgress(state.message, false);
                    }
                }, 2000);
            }

            micAddBtn.addEventListener('click', async () => {
                showMicProgress('Looking for the microphone… make sure it is plugged in.', false);
                try {
                    await fetch('/api/mic/provision', { method: 'POST' });  // 409 = already running; just follow it
                } catch (error) { /* keep polling */ }
                pollProvision();
            });

            async function updateRemoteHelpDot() {
                const dot = document.getElementById('remote-help-dot');
                try {
                    const status = await (await fetch('/api/remote_help/status')).json();
                    dot.classList.toggle('on', !!status.connected);
                } catch (error) {
                    dot.classList.remove('on');
                }
            }

```
In the existing `showSettingsModal`, after `settingsModal.style.display = 'flex';`, add:
```javascript
                updateRemoteHelpDot();
```
In the ESC handler chain, before `else if (confirmModal.style.display === 'flex') {`, add:
```javascript
                    else if (micModal.style.display === 'flex') hideMicModal();
```

- [ ] **Step 7: Run all tests**

Run: `.venv/bin/pytest -v`
Expected: all PASS.

- [ ] **Step 8: Visual check in a browser at 800×480**

Run: `.venv/bin/python birdnet_display.py` (BirdNET-Go won't be running locally; bird cards may show offline mode). Open `http://localhost:5000` at an 800×480 viewport, for example with Playwright `browser_resize` 800×480. Then:
1. Tap the bird area, then the settings icon, then **Microphone**. Expected: the modal shows "No microphone set up yet." and **Add microphone**.
2. Check that the Remote help dot is gray.
3. Tap the corner mic icon. Expected: the same modal opens.
4. Press ESC. Expected: it closes.
5. Take a screenshot to confirm the modal fits within 480 px height (it scrolls if not).

Stop the server.

- [ ] **Step 9: Commit**

```bash
git add static/index.html tests/test_index_html.py
git commit -m "Add Microphone screen and remote-help indicator to the touchscreen"
```

---

### Task 8: `setup_remote_help.sh` (bench-only WireGuard + SSH pre-load)

**Files:**
- Create: `setup_remote_help.sh`, `tests/test_setup_remote_help.py`

**Interfaces:**
- Produces a CLI:
  ```
  setup_remote_help.sh --endpoint HOST:PORT --server-pubkey KEY --address IP/32 --vpn-subnet CIDR [--lan-subnet CIDR] [--dry-run DIR]
  ```
  - It prompts for any missing value.
  - `--dry-run DIR` writes every file into DIR and touches nothing on the system.
  - Exit codes: 0 on success, 2 on bad input.
- Files written (real run → system path; dry run → `DIR/<basename>`):

  | File | Real path |
  |---|---|
  | `wg0.conf` | `/etc/wireguard/wg0.conf` |
  | `remote-help.key` | `/etc/wireguard/remote-help.key` |
  | `wg-reresolve` | `/usr/local/sbin/wg-reresolve` |
  | `wg-reresolve.service` | `/etc/systemd/system/wg-reresolve.service` |
  | `wg-reresolve.timer` | `/etc/systemd/system/wg-reresolve.timer` |
  | `50-remote-help.conf` | `/etc/ssh/sshd_config.d/50-remote-help.conf` |

- [ ] **Step 1: Write the failing tests**

Create `tests/test_setup_remote_help.py`:
```python
import os
import stat
import subprocess

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "setup_remote_help.sh")
PUBKEY = "A" * 43 + "="


def run(tmp_path, *extra, lan="192.168.86.0/24"):
    args = ["bash", SCRIPT, "--endpoint", "home.example.net:51820", "--server-pubkey", PUBKEY,
            "--address", "10.66.66.50/32", "--vpn-subnet", "10.66.66.0/24",
            "--lan-subnet", lan, "--dry-run", str(tmp_path), *extra]
    return subprocess.run(args, capture_output=True, text=True, stdin=subprocess.DEVNULL)


def test_dry_run_writes_split_tunnel_config(tmp_path):
    r = run(tmp_path)
    assert r.returncode == 0, r.stderr
    conf = (tmp_path / "wg0.conf").read_text()
    assert "Address = 10.66.66.50/32" in conf
    assert f"PublicKey = {PUBKEY}" in conf
    assert "Endpoint = home.example.net:51820" in conf
    assert "AllowedIPs = 10.66.66.0/24" in conf
    assert "PersistentKeepalive = 25" in conf
    assert "DNS" not in conf  # never take over the parents' DNS
    assert "[Peer]" in r.stdout and "AllowedIPs = 10.66.66.50/32" in r.stdout


def test_key_is_private_and_stable_across_reruns(tmp_path):
    run(tmp_path)
    key_path = tmp_path / "remote-help.key"
    mode = stat.S_IMODE(os.stat(key_path).st_mode)
    assert mode == 0o600
    first = key_path.read_text()
    run(tmp_path)
    assert key_path.read_text() == first


def test_reresolve_timer_every_5_minutes(tmp_path):
    run(tmp_path)
    assert "OnUnitActiveSec=5min" in (tmp_path / "wg-reresolve.timer").read_text()
    script = (tmp_path / "wg-reresolve").read_text()
    assert "wg set wg0 peer" in script and "home.example.net:51820" in script


def test_ssh_dropin_disables_passwords(tmp_path):
    run(tmp_path)
    assert "PasswordAuthentication no" in (tmp_path / "50-remote-help.conf").read_text()


def test_warns_on_subnet_overlap(tmp_path):
    r = run(tmp_path, lan="10.66.66.0/24")
    assert r.returncode == 0
    assert "overlaps" in (r.stdout + r.stderr).lower()


def test_rejects_bad_input(tmp_path):
    bad = subprocess.run(["bash", SCRIPT, "--endpoint", "no-port", "--server-pubkey", PUBKEY,
                          "--address", "10.66.66.50/32", "--vpn-subnet", "10.66.66.0/24",
                          "--dry-run", str(tmp_path)], capture_output=True, text=True,
                         stdin=subprocess.DEVNULL)
    assert bad.returncode == 2
    bad_key = subprocess.run(["bash", SCRIPT, "--endpoint", "h:1", "--server-pubkey", "short",
                              "--address", "10.66.66.50/32", "--vpn-subnet", "10.66.66.0/24",
                              "--dry-run", str(tmp_path)], capture_output=True, text=True,
                             stdin=subprocess.DEVNULL)
    assert bad_key.returncode == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_setup_remote_help.py -v`
Expected: FAIL (script missing; bash exit 127).

- [ ] **Step 3: Implement `setup_remote_help.sh`**

```bash
#!/bin/bash
# Pre-load WireGuard "remote help" on the BirdNET display. Run once on Chris's bench.
# The parents never run this. After it finishes, the tunnel comes up by itself wherever the Pi has internet.
set -euo pipefail

usage() {
    echo "Usage: $0 --endpoint HOST:PORT --server-pubkey KEY --address IP/32 --vpn-subnet CIDR [--lan-subnet CIDR] [--dry-run DIR]" >&2
    exit 2
}

ENDPOINT="" SERVER_PUBKEY="" ADDRESS="" VPN_SUBNET="" LAN_SUBNET="" DRY_RUN_DIR=""
while [ $# -gt 0 ]; do
    case "$1" in
        --endpoint) ENDPOINT="${2:-}"; shift 2 ;;
        --server-pubkey) SERVER_PUBKEY="${2:-}"; shift 2 ;;
        --address) ADDRESS="${2:-}"; shift 2 ;;
        --vpn-subnet) VPN_SUBNET="${2:-}"; shift 2 ;;
        --lan-subnet) LAN_SUBNET="${2:-}"; shift 2 ;;
        --dry-run) DRY_RUN_DIR="${2:-}"; shift 2 ;;
        *) usage ;;
    esac
done

ask() { local var="$1" prompt="$2"; if [ -z "${!var}" ]; then read -rp "$prompt" "$var" || true; fi; }
ask ENDPOINT "WireGuard server endpoint (your DDNS name:port): "
ask SERVER_PUBKEY "WireGuard server public key: "
ask ADDRESS "This display's VPN address (e.g. 10.66.66.50/32): "
ask VPN_SUBNET "Your VPN subnet (e.g. 10.66.66.0/24): "

fail() { echo "ERROR: $1" >&2; exit 2; }
[[ "$ENDPOINT" =~ ^[A-Za-z0-9.-]+:[0-9]{1,5}$ ]] || fail "endpoint must look like host:port"
[[ "$SERVER_PUBKEY" =~ ^[A-Za-z0-9+/]{43}=$ ]] || fail "server public key must be a 44-character WireGuard key"
python3 -c 'import ipaddress,sys; ipaddress.ip_interface(sys.argv[1]); ipaddress.ip_network(sys.argv[2], strict=False)' \
    "$ADDRESS" "$VPN_SUBNET" 2>/dev/null || fail "address/subnet must be CIDR, e.g. 10.66.66.50/32 and 10.66.66.0/24"

if [ -z "$LAN_SUBNET" ]; then
    LAN_SUBNET="$(ip -o -f inet addr show wlan0 2>/dev/null | awk '{print $4}' | head -1 || true)"
fi
if [ -n "$LAN_SUBNET" ] && python3 -c 'import ipaddress,sys; sys.exit(0 if ipaddress.ip_interface(sys.argv[1]).network.overlaps(ipaddress.ip_network(sys.argv[2], strict=False)) else 1)' "$LAN_SUBNET" "$VPN_SUBNET"; then
    echo "WARNING: this network ($LAN_SUBNET) overlaps your VPN subnet ($VPN_SUBNET). Routing will be confused — pick a different VPN subnet." >&2
fi

if [ -n "$DRY_RUN_DIR" ]; then
    mkdir -p "$DRY_RUN_DIR"
    out() { echo "$DRY_RUN_DIR/$(basename "$1")"; }
    write() { cat > "$(out "$1")"; }
    SUDO=""
else
    out() { echo "$1"; }
    write() { sudo tee "$1" > /dev/null; }
    SUDO="sudo"
    sudo apt-get install -y wireguard-tools openssh-server
    sudo mkdir -p /etc/wireguard && sudo chmod 700 /etc/wireguard
fi

KEY_FILE="$(out /etc/wireguard/remote-help.key)"
if ! $SUDO test -s "$KEY_FILE"; then
    if command -v wg >/dev/null 2>&1; then
        (umask 077; wg genkey | $SUDO tee "$KEY_FILE" > /dev/null)
    elif [ -n "$DRY_RUN_DIR" ]; then
        (umask 077; echo "dry-run-private-key-$RANDOM" > "$KEY_FILE")
    else
        fail "wg not found after installing wireguard-tools"
    fi
fi
$SUDO chmod 600 "$KEY_FILE"
PRIVATE_KEY="$($SUDO cat "$KEY_FILE")"
if command -v wg >/dev/null 2>&1 && [ -z "$DRY_RUN_DIR" -o "${PRIVATE_KEY#dry-run}" = "$PRIVATE_KEY" ]; then
    PUBLIC_KEY="$(echo "$PRIVATE_KEY" | wg pubkey)"
else
    PUBLIC_KEY="dry-run-public-key"
fi

(umask 077; write /etc/wireguard/wg0.conf <<EOF
# Remote help tunnel to Chris's home (split tunnel: only the VPN subnet goes through it)
[Interface]
PrivateKey = $PRIVATE_KEY
Address = $ADDRESS

[Peer]
PublicKey = $SERVER_PUBKEY
Endpoint = $ENDPOINT
AllowedIPs = $VPN_SUBNET
PersistentKeepalive = 25
EOF
)
$SUDO chmod 600 "$(out /etc/wireguard/wg0.conf)"

write /usr/local/sbin/wg-reresolve <<EOF
#!/bin/sh
# Re-resolve the DDNS endpoint so the tunnel follows Chris's home IP when it changes.
exec wg set wg0 peer "$SERVER_PUBKEY" endpoint "$ENDPOINT"
EOF
$SUDO chmod 755 "$(out /usr/local/sbin/wg-reresolve)"

write /etc/systemd/system/wg-reresolve.service <<'EOF'
[Unit]
Description=Re-resolve WireGuard remote-help endpoint
After=wg-quick@wg0.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/wg-reresolve
EOF

write /etc/systemd/system/wg-reresolve.timer <<'EOF'
[Unit]
Description=Re-resolve WireGuard remote-help endpoint every 5 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min

[Install]
WantedBy=timers.target
EOF

write /etc/ssh/sshd_config.d/50-remote-help.conf <<'EOF'
# Remote help: key-only SSH
PasswordAuthentication no
KbdInteractiveAuthentication no
EOF

if [ -z "$DRY_RUN_DIR" ]; then
    if [ ! -s "$HOME/.ssh/authorized_keys" ]; then
        sudo rm -f /etc/ssh/sshd_config.d/50-remote-help.conf
        echo "WARNING: no ~/.ssh/authorized_keys yet — left password SSH on. Add your key (ssh-copy-id) and re-run." >&2
    fi
    sudo systemctl daemon-reload
    sudo systemctl enable --now ssh wg-quick@wg0 wg-reresolve.timer
    sudo systemctl reload ssh || true
fi

ADDR_ONLY="${ADDRESS%/*}"
cat <<EOF

Add this to your WireGuard SERVER config, then reload it:

[Peer]
# BirdNET display (parents)
PublicKey = $PUBLIC_KEY
AllowedIPs = $ADDR_ONLY/32

Then from anywhere on your VPN:  ssh $(whoami)@$ADDR_ONLY
Mic web page:                    ssh -L 8081:<mic-ip>:80 $(whoami)@$ADDR_ONLY  →  http://localhost:8081
EOF
```

- [ ] **Step 4: Run all tests**

Run: `chmod +x setup_remote_help.sh && .venv/bin/pytest -v`
Expected: all PASS. If available, also run `shellcheck setup_remote_help.sh`. Expected: no errors; style warnings are OK.

- [ ] **Step 5: Commit**

```bash
git add setup_remote_help.sh tests/test_setup_remote_help.py
git commit -m "Add bench script to pre-load WireGuard remote help"
```

---

### Task 9: Installer, fan control, and docs

**Files:**
- Modify: `install.sh` (Step 3 copy block at about lines 52–59; new Step 10b after the kiosk block, before `# --- Step 11`), `README.md`

**Interfaces:**
- Consumes: all files from Tasks 1–8.

- [ ] **Step 1: Copy the new files in `install.sh` Step 3**

After `cp "$SOURCE_DIR/species_list.csv" "$INSTALL_DIR/"`, add:
```bash
for f in mic_manager.py mic_service.py mic_provisioner.py mic_routes.py birdnet_go_config.py remote_help.py rtsp_monitor.py setup_remote_help.sh; do
    cp "$SOURCE_DIR/$f" "$INSTALL_DIR/"
done
chmod +x "$INSTALL_DIR/setup_remote_help.sh"
```

- [ ] **Step 2: Add the mDNS dependencies and a fan prompt**

Immediately before the line `# --- Step 11: Optional BirdNET-Go Network Configuration ---`, add:
```bash
# --- Step 10b: Outdoor mic discovery (mDNS) ---
echo -e "\n${YELLOW}Step 10b: Ensuring mDNS (avahi) is available for finding the outdoor mic...${NC}"
sudo apt-get install -y avahi-daemon libnss-mdns
sudo systemctl enable --now avahi-daemon
echo -e "${GREEN}✅ mDNS ready.${NC}"

# --- Step 10c: Optional quiet fan control ---
echo ""
read -p "Is the heatsink fan's control wire on GPIO14? Turn the fan on only above 70°C? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    BOOT_CONFIG="/boot/firmware/config.txt"
    [ -f "$BOOT_CONFIG" ] || BOOT_CONFIG="/boot/config.txt"
    if ! grep -q '^dtoverlay=gpio-fan' "$BOOT_CONFIG"; then
        echo "dtoverlay=gpio-fan,gpiopin=14,temp=70000" | sudo tee -a "$BOOT_CONFIG" > /dev/null
        echo -e "${GREEN}✅ Fan set to switch on at 70°C (after reboot).${NC}"
        REBOOT_REQUIRED=true
    else
        echo -e "${GREEN}✅ Fan overlay already configured.${NC}"
    fi
fi

echo -e "\n${YELLOW}Remote help: on your bench, run ${NC}$INSTALL_DIR/setup_remote_help.sh${YELLOW} once to pre-load WireGuard.${NC}"
```

- [ ] **Step 3: Syntax check**

Run: `bash -n install.sh && bash -n setup_remote_help.sh && echo ok`
Expected: `ok`.

- [ ] **Step 4: README section**

After the `### Access Point (AP) Setup for ESP32 Microphone` section (before `### Web Interface Controls`), add:
```markdown
### Outdoor Wi-Fi Microphone (home Wi-Fi, set up from the touchscreen)

This fork supports an outdoor ESP32 mic ([birdnetgo-esp32-rtsp-mic](https://github.com/Sukecz/birdnetgo-esp32-rtsp-mic) v1.26+) on your **home Wi-Fi**. No USB Wi-Fi adapter or `ap_setup.sh` is needed.

1. Make sure the display is on your Wi-Fi (Settings → Open WiFi Settings).
2. Plug in the mic. A brand-new mic broadcasts the setup network `ESP32-RTSP-Mic-AP`.
3. Settings → **Microphone** → **Add microphone**. The display is offline for about a minute while it hands your Wi-Fi details to the mic, then finds it and points BirdNET-Go at it.

The Microphone screen shows signal, temperature, and streaming status. It has controls for sensitivity, wind/traffic noise reduction, restart, and remove. If the mic's IP changes, the display finds it again automatically.

Design and parts: `docs/superpowers/specs/2026-10-14-outdoor-wifi-mic-design.md`, `docs/parts-list.md`.

### Remote Help (WireGuard)

Run `./setup_remote_help.sh` once on your own network before gifting. It:
- generates the display's key
- writes a split-tunnel `wg0.conf` to your WireGuard server
- re-resolves your DDNS name every 5 minutes
- switches SSH to keys only
- prints the `[Peer]` block to add to your server

The Settings screen shows a green **Remote help** dot when the tunnel is up.
```

- [ ] **Step 5: Run the full suite and commit**

Run: `.venv/bin/pytest -v`
Expected: all PASS.
```bash
git add install.sh README.md
git commit -m "Installer: copy mic modules, mDNS, optional quiet fan; document mic and remote help"
```

---

### Task 10: Bench integration (real hardware, Chris's desk)

No code unless a check fails. A failure goes back to the owning task as a bug fix with a regression test.

**Files:** none (record results in `docs/research/bench-results.md`)

- [ ] **Step 1: Prepare the Pi.**
  1. Flash Raspberry Pi OS Bookworm (desktop) to the Kingston card and boot.
  2. Join your home Wi-Fi.
  3. Clone your fork, check out `outdoor-wifi-mic`, and run `./install.sh`. Answer **y** to kiosk and to the fan prompt if wired.
  4. Reboot.
- [ ] **Step 2: Prepare the mic.**
  1. Flash the XIAO C3 at https://esp32mic.msmeteo.cz.
  2. Wire the SPH0645 per `docs/research/sourcing-notes.md` (use the **C3 GPIO** column), attach the included FPC antenna, and power from USB.
  3. Leave it unconfigured, so it broadcasts `ESP32-RTSP-Mic-AP`.
- [ ] **Step 3: Add the mic.** Touchscreen → Settings → Microphone → Add microphone.
  - Expected: progress messages, the display back on Wi-Fi within about 90 s, then "Microphone added!".
  - Check: `cat ~/birdnet_display/mic_config.json` and `grep -A4 "Outdoor Mic" ~/birdnet-go-app/config/config.yaml`.
- [ ] **Step 4: Confirm the firmware fields.** Run `curl -s http://<mic-ip>/api/status | python3 -m json.tool`.
  - Confirm `hp_enable`, `gain`, `temperature_c`, `wifi_rssi`, `streaming`, and `mdns_hostname` are present.
  - If `hp_enable` is missing from `/api/status`, find the endpoint that reports it and update `summarize_status` (Task 1) with a test.
- [ ] **Step 5: Confirm mDNS.** Run `avahi-browse -rt _http._tcp | grep -i esp32mic`. The instance name must start with `esp32mic-`. If it's different, adjust `browse_mdns` matching (Task 2) with a test.
- [ ] **Step 6: Confirm detections.** Play bird audio near the mic (for example an Xeno-canto clip). Expected: a detection shows on the display within a minute.
- [ ] **Step 7: Change settings from the touchscreen.** Change the gain and toggle noise reduction. Verify on the mic's own web UI (`http://<mic-ip>/`).
- [ ] **Step 8: Unplug the mic.**
  - Expected: within about 10 s the corner icon goes gray and the Microphone screen says "not responding".
  - Plug it back in. Expected: it recovers within about 1 minute.
- [ ] **Step 9: IP change.** Give the mic a different DHCP reservation on your router and reboot the mic. Expected: within about 2 minutes `mic_config.json` and BirdNET-Go's config show the new IP.
- [ ] **Step 10: Failure paths.**
  - Tap Add microphone with the mic unplugged. Expected: "Couldn't find the microphone… unplug…", and the display is still on Wi-Fi.
  - Start setup, then pull the mic's power mid-handoff. Expected: the display reconnects to home Wi-Fi and shows an error.
- [ ] **Step 11: Remote help.**
  1. Run `./setup_remote_help.sh` with your DDNS endpoint and add the printed `[Peer]` to your server.
  2. From your phone hotspot (off your LAN), run `ssh` to the Pi's VPN IP.
  3. Run `ssh -L 8081:<mic-ip>:80 …` and open `http://localhost:8081`.
  4. Reboot the Pi. Expected: the tunnel returns unattended, and the dot is green in Settings.
- [ ] **Step 12: Thermal.**
  1. Run `for i in $(seq 1 288); do date +%T; vcgencmd measure_temp; vcgencmd get_throttled; sleep 300; done > ~/thermal.log` for 24 h with BirdNET-Go and the kiosk running.
  2. Record the max temperature.
  3. If it never nears 70 °C, note that the fan can be unplugged.
- [ ] **Step 12b: Recovery checks (from the final code review).**
  - Kill `bird-display` mid-setup with `sudo systemctl restart bird-display`. Expected: the `birdnet-mic-watchdog` timer brings home Wi-Fi back within about 3 minutes.
  - Boot the Pi with no network, then join Wi-Fi. Expected: `wg0` comes up within about 5 minutes via `wg-reresolve`.
  - Make the BirdNET-Go restart fail once (for example `sudo systemctl mask birdnet-go` during setup, then unmask). Expected: the next monitor pass restarts it.
  - Use a test SSID containing `:` and `\`, and confirm the mic joins.
  - Run `curl /api/status` and confirm `mdns_hostname` matches `mic_config.json`.

- [ ] **Step 13: Record and commit results**

Write `docs/research/bench-results.md` with the date, pass/fail per step, measured values (setup time, RSSI at the intended mount distance, max Pi temp), and any fixes made. Then:
```bash
git add docs/research/bench-results.md
git commit -m "Record bench integration results"
```
