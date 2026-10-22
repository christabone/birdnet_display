import os
import subprocess

ROOT = os.path.join(os.path.dirname(__file__), "..")
INSTALL = open(os.path.join(ROOT, "install.sh")).read()

NEW_FILES = ["mic_manager.py", "mic_service.py", "mic_provisioner.py", "mic_routes.py",
             "birdnet_go_config.py", "remote_help.py", "rtsp_monitor.py", "setup_remote_help.sh"]


def test_installer_copies_every_mic_module():
    for name in NEW_FILES:
        assert name in INSTALL, name


def test_installer_sets_up_mdns_and_optional_fan():
    assert "avahi-daemon" in INSTALL and "libnss-mdns" in INSTALL
    assert "dtoverlay=gpio-fan,gpiopin=14,temp=70000" in INSTALL


def test_installer_is_valid_bash():
    assert subprocess.run(["bash", "-n", os.path.join(ROOT, "install.sh")]).returncode == 0


def _sudoers_rules():
    """The sudoers heredoc install.sh writes, with its command-path variables filled in."""
    body = INSTALL.split("<< SUDOERS_EOF\n", 1)[1].split("\nSUDOERS_EOF", 1)[0]
    paths = {"$CURRENT_USER": "pi", "$SYSTEMCTL": "/usr/bin/systemctl", "$SYSTEMD_RUN": "/usr/bin/systemd-run",
             "$WG": "/usr/bin/wg", "$REBOOT": "/usr/sbin/reboot", "$POWEROFF": "/usr/sbin/poweroff",
             "$TEE": "/usr/bin/tee"}
    for var, value in paths.items():
        body = body.replace(var, value)
    return body


def test_installer_grants_only_the_commands_the_app_needs_without_a_password():
    # Trixie images don't give the user passwordless sudo, and the app runs these from a service with no tty.
    rules = _sudoers_rules()
    assert "/etc/sudoers.d/birdnet-display" in INSTALL
    assert "visudo -cf" in INSTALL  # a broken sudoers file would lock out sudo entirely
    for needed in ["/usr/bin/systemctl restart birdnet-go.service",
                   "/usr/bin/systemctl stop birdnet-mic-watchdog.timer",
                   "/usr/bin/systemd-run ^--unit=birdnet-mic-watchdog ",
                   "/usr/bin/wg show wg0 latest-handshakes",
                   "/usr/sbin/reboot", "/usr/sbin/poweroff",
                   "/usr/bin/tee /sys/class/backlight/10-0045/brightness"]:
        assert needed in rules, needed
    assert "ALL=(ALL) NOPASSWD: ALL" not in rules


def test_sudoers_watchdog_rule_matches_what_the_provisioner_runs():
    import re
    from mic_provisioner import WATCHDOG_SECONDS, WATCHDOG_UNIT
    line = next(l for l in _sudoers_rules().splitlines() if "systemd-run" in l)
    pattern = line.split("/usr/bin/systemd-run ", 1)[1]
    args = (f"--unit={WATCHDOG_UNIT} --on-active={WATCHDOG_SECONDS} --timer-property=AccuracySec=1s "
            "nmcli con up 75a1216a-9d1a-30cd-8aca-ace5526ec021")
    assert re.fullmatch(pattern.strip("^$"), args)
    assert not re.fullmatch(pattern.strip("^$"), args + " ; rm -rf /")


def test_sudoers_rules_pass_visudo(tmp_path):
    import shutil
    import pytest
    visudo = shutil.which("visudo") or "/usr/sbin/visudo"
    if not os.path.exists(visudo):
        pytest.skip("visudo not installed")
    f = tmp_path / "birdnet-display"
    f.write_text(_sudoers_rules() + "\n")
    r = subprocess.run([visudo, "-cf", str(f)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
