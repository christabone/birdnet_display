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
