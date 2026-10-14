"""Touchscreen API for the outdoor mic and remote help."""
from dataclasses import asdict

from flask import Blueprint, jsonify, request

from mic_manager import MicClient, MicError, summarize_status
from remote_help import remote_help_status


def create_mic_blueprint(service, provisioner, remote_status=remote_help_status,
                         client_factory=MicClient):
    bp = Blueprint("mic", __name__)

    def saved_mic():
        return service.config.load()

    @bp.get("/api/mic/status")
    def mic_status():
        mic = saved_mic()
        if mic is None:
            return jsonify({"configured": False})
        base = {"configured": True, "hostname": mic.hostname, "ip": mic.ip}
        try:
            raw = client_factory(mic.ip, timeout=2).get_status()
        except MicError:
            return jsonify({**base, "reachable": False})
        return jsonify({**base, **summarize_status(raw)})

    @bp.post("/api/mic/settings")
    def mic_settings():
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or not ({"gain", "highpass_enabled"} & body.keys()):
            return jsonify({"status": "error", "message": "Nothing to change"}), 400
        if "highpass_enabled" in body and not isinstance(body["highpass_enabled"], bool):
            return jsonify({"status": "error", "message": "highpass_enabled must be true/false"}), 400
        if "gain" in body:
            try:
                float(body["gain"])
            except (TypeError, ValueError):
                return jsonify({"status": "error", "message": "gain must be a number"}), 400
        mic = saved_mic()
        if mic is None:
            return jsonify({"status": "error", "message": "No microphone set up"}), 409
        client = client_factory(mic.ip)
        try:
            if "gain" in body:
                client.set_gain(float(body["gain"]))
            if "highpass_enabled" in body:
                client.set_highpass(body["highpass_enabled"])
        except ValueError as e:
            return jsonify({"status": "error", "message": str(e)}), 400
        except MicError:
            return jsonify({"status": "error", "message": "Microphone not responding"}), 502
        return jsonify({"status": "ok"})

    @bp.post("/api/mic/restart")
    def mic_restart():
        mic = saved_mic()
        if mic is None:
            return jsonify({"status": "error", "message": "No microphone set up"}), 409
        try:
            client_factory(mic.ip).restart()
        except MicError:
            return jsonify({"status": "error", "message": "Microphone not responding"}), 502
        return jsonify({"status": "ok"})

    @bp.post("/api/mic/forget")
    def mic_forget():
        service.config.forget()
        return jsonify({"status": "ok"})

    @bp.post("/api/mic/provision")
    def mic_provision():
        if not provisioner.start():
            return jsonify({"status": "already_running"}), 409
        return jsonify({"status": "started"}), 202

    @bp.get("/api/mic/provision/status")
    def mic_provision_status():
        return jsonify(asdict(provisioner.state))

    @bp.get("/api/remote_help/status")
    def remote_help():
        return jsonify(remote_status())

    return bp
