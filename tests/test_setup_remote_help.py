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
