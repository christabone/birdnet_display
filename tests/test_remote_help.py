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
