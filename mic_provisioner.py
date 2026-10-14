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

    def wifi_security(self, con):
        """Key management of a saved Wi-Fi profile ('' = open network)."""
        return self._field(con, "802-11-wireless-security.key-mgmt").strip()

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
        # Check the display's own Wi-Fi first: no point scanning for the mic if we can't hand anything over.
        self._step("read_home_wifi", "Reading your Wi-Fi details…")
        home = self.net.active_connection()
        if not home:
            raise ProvisionError("The display needs to be connected to Wi-Fi first.")
        if home == SETUP_CON_NAME:
            raise ProvisionError("The display is still on the microphone's setup network. Restart the display, then try again.")
        ssid, psk = self.net.wifi_credentials(home)
        if not ssid:
            raise ProvisionError("The display needs to be connected to Wi-Fi first.")
        security = self.net.wifi_security(home)
        if security == "wpa-eap":
            raise ProvisionError("This kind of Wi-Fi (enterprise login) can't be shared with the microphone. Please ask Chris for help.")
        if security and not psk:
            raise ProvisionError("The display couldn't read your Wi-Fi password. Please ask Chris for help.")
        self._step("find_setup_network", "Looking for the microphone…")
        if not self._wait_for_setup_network():
            raise ProvisionError("Couldn't find the microphone. Unplug its power for 5 seconds, plug it back in, then try again.")
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
