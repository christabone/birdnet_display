#!/usr/bin/env python3
"""
RTSP Connection Monitor
Checks if last_rtsp_connect matches last_stream_start, and reboots if they differ.
"""

import requests
import sys

import json
import os

# Configuration: the mic's address comes from the display's saved mic (mic_config.json).
MIC_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mic_config.json")
TIMEOUT = 10  # seconds


def _mic_ip():
    with open(MIC_CONFIG_PATH) as f:
        return json.load(f)["ip"]


try:
    _IP = _mic_ip()
except (OSError, ValueError, KeyError):
    print(f"No mic configured ({MIC_CONFIG_PATH}); nothing to check.")
    sys.exit(0)

STATUS_URL = f"http://{_IP}/api/status"
REBOOT_URL = f"http://{_IP}/api/action/reboot"


def check_status():
    """Check RTSP connection status and reboot if necessary."""
    try:
        print(f"Checking status at {STATUS_URL}")
        response = requests.get(STATUS_URL, timeout=TIMEOUT)
        response.raise_for_status()
        
        data = response.json()
        
        last_rtsp_connect = data.get('last_rtsp_connect')
        last_stream_start = data.get('last_stream_start')
        
        print(f"last_rtsp_connect: {last_rtsp_connect}")
        print(f"last_stream_start: {last_stream_start}")
        
        # Check if values match
        if last_rtsp_connect != last_stream_start:
            print("MISMATCH detected - triggering reboot")
            requests.post(REBOOT_URL, headers={"X-ESP32MIC-CSRF": "1"}, timeout=TIMEOUT)
            print("Reboot command sent")
        else:
            print("Status OK - times match")
        
        return 0
                
    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(check_status())