"""Keep track of the outdoor mic: re-find it if its IP changes, keep BirdNET-Go pointed at it."""
import threading
import time

from birdnet_go_config import point_birdnet_go_at
from mic_manager import MicClient, MicError, discover, is_same_mic

STATUS_TIMEOUT = 2


class MicService:
    def __init__(self, config, client_factory=MicClient, discover_fn=discover,
                 update_birdnet=point_birdnet_go_at):
        self.config = config
        self.client_factory = client_factory
        self.discover_fn = discover_fn
        self.update_birdnet = update_birdnet

    def _status(self, ip):
        return self.client_factory(ip, timeout=STATUS_TIMEOUT).get_status()

    def refresh_once(self, busy=lambda: False):
        if busy():
            return
        saved = self.config.load()
        if saved is None:
            return
        current = saved
        try:
            if not is_same_mic(self._status(saved.ip), saved.hostname):
                raise MicError(f"another mic answered at {saved.ip}")
        except MicError:
            current = self.discover_fn(saved=saved)
            if current is None:
                return
            if current != saved:
                self.config.save(current)
                print(f"[INFO] Mic moved to {current.ip}")
        try:
            self.update_birdnet(current.ip)
        except Exception as e:
            print(f"[WARN] Could not update BirdNET-Go for mic {current.ip}: {e}")

    def start_background(self, busy, interval=60):
        def loop():
            while True:
                try:
                    self.refresh_once(busy=busy)
                except Exception as e:
                    print(f"[WARN] Mic monitor error: {e}")
                time.sleep(interval)
        thread = threading.Thread(target=loop, name="mic-monitor", daemon=True)
        thread.start()
        return thread

    def audio_status(self):
        mic = self.config.load()
        if mic is None:
            return {"connected": False, "rssi": 0}
        try:
            raw = self._status(mic.ip)
        except MicError:
            return {"connected": False, "rssi": 0}
        return {"connected": raw.get("streaming") is True, "rssi": raw.get("wifi_rssi", 0)}
