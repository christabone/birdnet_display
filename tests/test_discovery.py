from mic_manager import MicError, MicInfo, discover


def make_factory(alive_ips):
    class Client:
        def __init__(self, ip, **kwargs):
            self.ip = ip

        def get_status(self):
            if self.ip not in alive_ips:
                raise MicError("down")
            return {"streaming": True}
    return Client


def test_first_add_picks_new_mic_and_ignores_known_ones():
    found = [("esp32mic-neighbor", "192.168.1.40"), ("esp32mic-new", "192.168.1.77")]
    result = discover(ignore=frozenset({"esp32mic-neighbor"}), browse=lambda: found,
                      client_factory=make_factory({"192.168.1.40", "192.168.1.77"}))
    assert result == MicInfo("esp32mic-new", "192.168.1.77")


def test_first_add_skips_unresponsive():
    found = [("esp32mic-a", "192.168.1.40"), ("esp32mic-b", "192.168.1.41")]
    result = discover(browse=lambda: found, client_factory=make_factory({"192.168.1.41"}))
    assert result == MicInfo("esp32mic-b", "192.168.1.41")


def test_saved_mic_found_at_new_ip():
    saved = MicInfo("esp32mic-ours", "192.168.1.50")
    found = [("esp32mic-spare", "192.168.1.60"), ("esp32mic-ours", "192.168.1.51")]
    result = discover(saved=saved, browse=lambda: found,
                      client_factory=make_factory({"192.168.1.51", "192.168.1.60"}))
    assert result == MicInfo("esp32mic-ours", "192.168.1.51")


def test_saved_mic_falls_back_to_last_ip_when_mdns_silent():
    saved = MicInfo("esp32mic-ours", "192.168.1.50")
    result = discover(saved=saved, browse=lambda: [],
                      client_factory=make_factory({"192.168.1.50"}))
    assert result == saved


def test_saved_mic_never_swaps_to_another_mic():
    saved = MicInfo("esp32mic-ours", "192.168.1.50")
    found = [("esp32mic-spare", "192.168.1.60")]
    assert discover(saved=saved, browse=lambda: found,
                    client_factory=make_factory({"192.168.1.60"})) is None


def test_nothing_found():
    assert discover(browse=lambda: [], client_factory=make_factory(set())) is None
