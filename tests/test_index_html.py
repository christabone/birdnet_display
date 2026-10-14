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


def _function_body(name):
    start = HTML.index(f"function {name}(")
    return HTML[start:HTML.index("\n            }\n", start)]


def test_reopening_mic_screen_resumes_running_setup():
    assert "resumeProvisionIfRunning()" in _function_body("showMicModal")
    body = _function_body("resumeProvisionIfRunning")
    assert "'/api/mic/provision/status'" in body and "pollProvision()" in body


def test_restart_and_remove_report_failures():
    for label in ["Restart the microphone?", "Remove this microphone from the display?"]:
        handler = HTML[HTML.index(label):HTML.index("\n                });", HTML.index(label))]
        assert "response.ok" in handler and "catch" in handler, label
