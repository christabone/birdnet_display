"""Is the WireGuard 'remote help' tunnel to Chris's home up?"""
import subprocess
import time


def remote_help_status(run=subprocess.run, now=time.time, iface="wg0", fresh_seconds=180):
    try:
        r = run(["sudo", "-n", "wg", "show", iface, "latest-handshakes"],
                capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return {"configured": False, "connected": False, "last_handshake_seconds": None}
    if r.returncode != 0:
        return {"configured": False, "connected": False, "last_handshake_seconds": None}
    latest = 0
    for line in r.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) == 2 and parts[1].strip().isdigit():
            latest = max(latest, int(parts[1]))
    if latest == 0:
        return {"configured": True, "connected": False, "last_handshake_seconds": None}
    age = max(0, int(now() - latest))
    return {"configured": True, "connected": age < fresh_seconds, "last_handshake_seconds": age}
