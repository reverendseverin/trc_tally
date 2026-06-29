#!/usr/bin/env python3
"""Flask web layer: auth, REST API, and an SSE stream over the Core."""

import json
import logging
import os
import queue
from functools import wraps

from flask import (Flask, Response, jsonify, request, session,
                   send_from_directory, render_template, abort)

from tally_core import (STATE_LABEL, AUTO_CODES, fetch_vmix_inputs,
                        list_serial_ports, provision_tally, reset_tally,
                        resource_path)

log = logging.getLogger("trc_tally.web")


def create_app(core, secret_key):
    app = Flask(__name__, static_folder=resource_path("static"),
                template_folder=resource_path("templates"))
    app.secret_key = secret_key

    # -- auth --------------------------------------------------------------- #
    def login_required(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not session.get("authed"):
                abort(401)
            return fn(*args, **kwargs)
        return wrapper

    @app.post("/login")
    def login():
        password = (request.json or {}).get("password", "")
        if password == core.config.web.get("password"):
            session["authed"] = True
            return jsonify(ok=True)
        return jsonify(ok=False, error="Incorrect password"), 403

    @app.get("/logout")
    def logout():
        session.clear()
        return jsonify(ok=True)

    @app.get("/api/session")
    def session_status():
        return jsonify(authed=bool(session.get("authed")))

    # -- pages / static ----------------------------------------------------- #
    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/tally.svg")
    def tally_svg():
        return send_from_directory(os.path.dirname(resource_path("tally.svg")), "tally.svg")

    @app.get("/favicon.ico")
    def favicon():
        return ("", 204)

    # -- config snapshot ---------------------------------------------------- #
    @app.get("/api/config")
    @login_required
    def get_config():
        return jsonify(machines=core.config.machines(), tallies=core.config.tallies(),
                       state_labels=STATE_LABEL, auto_codes=sorted(AUTO_CODES),
                       mqtt=core.config.mqtt)

    @app.get("/api/state")
    @login_required
    def get_state():
        snap = core.state.snapshot()
        return jsonify(snap)

    # -- settings (web + mqtt) --------------------------------------------- #
    @app.get("/api/settings")
    @login_required
    def get_settings():
        web, mq = core.config.web, core.config.mqtt
        return jsonify(port=web.get("port"), has_password=bool(web.get("password")),
                       broker_ip=mq.get("broker_ip"), broker_port=mq.get("broker_port"))

    @app.post("/api/settings")
    @login_required
    def update_settings():
        body = request.json or {}
        old_mqtt, old_port = core.config.mqtt, core.config.web.get("port")
        core.config.update_web(body)
        mq = core.config.update_mqtt(body)
        broker_changed = (mq["broker_ip"], mq["broker_port"]) != (old_mqtt["broker_ip"], old_mqtt["broker_port"])
        if broker_changed:
            core.mqtt.reconnect(mq["broker_ip"], mq["broker_port"])
        # The web port can't be rebound live — flag if it changed.
        port_changed = bool(core.config.web.get("port") != old_port)
        return jsonify(ok=True, broker_changed=broker_changed, restart_required=port_changed)

    # -- machines ----------------------------------------------------------- #
    @app.post("/api/machines")
    @login_required
    def add_machine():
        machine = core.config.add_machine(request.json or {})
        core.state.update_machine(machine["id"], connected=False)
        core.pollers.start(machine["id"])
        return jsonify(machine)

    @app.put("/api/machines/<mid>")
    @login_required
    def update_machine(mid):
        machine = core.config.update_machine(mid, request.json or {})
        if machine is None:
            abort(404)
        core.pollers.restart(mid)  # pick up URL/refresh changes
        return jsonify(machine)

    @app.delete("/api/machines/<mid>")
    @login_required
    def delete_machine(mid):
        core.pollers.stop(mid)
        core.config.delete_machine(mid)
        return jsonify(ok=True)

    @app.get("/api/machines/<mid>/inputs")
    @login_required
    def machine_inputs(mid):
        machine = core.config.machine(mid)
        if machine is None:
            abort(404)
        try:
            return jsonify(inputs=fetch_vmix_inputs(machine["url"]))
        except Exception as exc:  # network/parse errors -> empty list + reason
            return jsonify(inputs=[], error=str(exc)), 502

    @app.post("/api/machines/<mid>/restart")
    @login_required
    def restart_machine(mid):
        if core.config.machine(mid) is None:
            abort(404)
        core.pollers.restart(mid)
        return jsonify(ok=True)

    @app.post("/api/machines/<mid>/mode")
    @login_required
    def set_mode(mid):
        mode = (request.json or {}).get("mode")
        if mode not in ("live", "manual"):
            abort(400)
        if core.config.machine(mid) is None:
            abort(404)
        core.state.set_mode(mid, mode)
        return jsonify(ok=True, mode=mode)

    # -- tallies ------------------------------------------------------------ #
    @app.post("/api/tallies")
    @login_required
    def add_tally():
        return jsonify(core.config.add_tally(request.json or {}))

    @app.put("/api/tallies/<tid>")
    @login_required
    def update_tally(tid):
        tally = core.config.update_tally(tid, request.json or {})
        if tally is None:
            abort(404)
        return jsonify(tally)

    @app.delete("/api/tallies/<tid>")
    @login_required
    def delete_tally(tid):
        core.config.delete_tally(tid)
        return jsonify(ok=True)

    @app.post("/api/tallies/<tid>/assign")
    @login_required
    def assign_tally(tid):
        machine_id = (request.json or {}).get("machine_id")  # may be None (unassign)
        tally = core.config.update_tally(tid, {"machine_id": machine_id})
        if tally is None:
            abort(404)
        core.bus.publish({"type": "config"})
        return jsonify(tally)

    @app.post("/api/tallies/<tid>/command")
    @login_required
    def command_tally(tid):
        code = (request.json or {}).get("code")
        tally = core.config.tally(tid)
        if tally is None:
            abort(404)
        if tally.get("machine_id") and core.state.get_mode(tally["machine_id"]) != "manual":
            return jsonify(ok=False, error="Machine must be in manual mode to send test commands"), 409
        core.send_command(tally, int(code))
        return jsonify(ok=True)

    # -- serial provisioning ----------------------------------------------- #
    @app.get("/api/serial/ports")
    @login_required
    def serial_ports():
        return jsonify(ports=list_serial_ports())

    @app.post("/api/serial/provision")
    @login_required
    def serial_provision():
        body = request.json or {}
        port = body.get("port")
        if not port:
            return jsonify(ok=False, error="No serial port selected"), 400
        return jsonify(provision_tally(port, body))

    @app.post("/api/serial/reset")
    @login_required
    def serial_reset():
        body = request.json or {}
        port = body.get("port")
        if not port:
            return jsonify(ok=False, error="No serial port selected"), 400
        return jsonify(reset_tally(port))

    # -- SSE ---------------------------------------------------------------- #
    @app.get("/api/events")
    @login_required
    def events():
        def stream():
            q = core.bus.subscribe()
            try:
                yield "retry: 2000\n\n"
                while True:
                    try:
                        event = q.get(timeout=15)
                        yield f"data: {json.dumps(event)}\n\n"
                    except queue.Empty:
                        yield ": keepalive\n\n"  # comment frame keeps the connection open
            finally:
                core.bus.unsubscribe(q)
        return Response(stream(), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    return app
