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
