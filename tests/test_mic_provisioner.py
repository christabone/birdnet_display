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
