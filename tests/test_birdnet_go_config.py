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
