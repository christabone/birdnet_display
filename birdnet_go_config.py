"""Keep BirdNET-Go's RTSP input pointed at the outdoor mic."""
import os
import shutil
import subprocess
import tempfile
import threading

from ruamel.yaml import YAML

DEFAULT_CONFIG_PATH = os.path.expanduser("~/birdnet-go-app/config/config.yaml")
STREAM_NAME = "Outdoor Mic"
# The upstream project's Pi-hosted mic network (ap_setup.sh) always put the mic here.
LEGACY_MIC_HOST = "10.42.0.50"
_write_lock = threading.Lock()


def mic_rtsp_url(ip):
    return f"rtsp://{ip}:8554/audio1"


def _is_legacy(stream):
    return stream.get("name") != STREAM_NAME and f"://{LEGACY_MIC_HOST}:" in str(stream.get("url", ""))


def set_mic_stream(url, config_path=DEFAULT_CONFIG_PATH):
    """Add or update the 'Outdoor Mic' stream. Returns True if the file changed.

    Also drops the old Pi-hosted-AP mic stream (10.42.0.50), which can never connect on home Wi-Fi.
    """
    with _write_lock:
        yaml = YAML()  # round-trip mode keeps comments and ordering
        with open(config_path) as f:
            data = yaml.load(f) or {}
        realtime = data.setdefault("realtime", {})
        rtsp = realtime.setdefault("rtsp", {})
        streams = rtsp.get("streams") or []
        legacy = [s for s in streams if _is_legacy(s)]
        for s in legacy:
            streams.remove(s)
        changed = bool(legacy)
        for stream in streams:
            if stream.get("name") == STREAM_NAME:
                if stream.get("url") != url:
                    stream["url"] = url
                    changed = True
                break
        else:
            streams.append({"name": STREAM_NAME, "url": url, "type": "rtsp", "transport": "tcp"})
            changed = True
        if not changed:
            return False
        rtsp["streams"] = streams
        directory = os.path.dirname(os.path.abspath(config_path))
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=".config.", suffix=".yaml")
        try:
            with os.fdopen(fd, "w") as f:
                yaml.dump(data, f)
            shutil.copymode(config_path, tmp)  # keep BirdNET-Go's 0600 (the file holds secrets)
            os.replace(tmp, config_path)
        except BaseException:
            os.unlink(tmp)
            raise
        return True


def restart_birdnet_go(run=subprocess.run):
    run(["sudo", "-n", "systemctl", "restart", "birdnet-go.service"],
        check=True, capture_output=True, text=True, timeout=90)


def point_birdnet_go_at(ip, config_path=DEFAULT_CONFIG_PATH, run=subprocess.run):
    """Make BirdNET-Go listen to the mic at `ip`. Returns True if it was changed.

    A marker file records a restart that is still owed, so a restart that fails after the
    config was written is retried on the next call instead of being lost.
    """
    pending = config_path + ".restart-pending"
    changed = set_mic_stream(mic_rtsp_url(ip), config_path)
    if changed:
        open(pending, "w").close()
    if os.path.exists(pending):
        restart_birdnet_go(run=run)
        os.remove(pending)
    return changed
