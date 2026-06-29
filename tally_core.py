#!/usr/bin/env python3
"""Core logic for the TRC Tally web service.

Holds configuration, the MQTT transport, one poller thread per vMix machine, and
the live runtime state that the web layer reads and streams to the browser.

The actual tally protocol (cloud = MQTT state code on the upper-cased MAC topic;
local = WLED DRGB UDP packet) matches the vendor firmware. See README for the
state-code table.
"""

import copy
import json
import logging
import os
import queue
import socket
import sys
import threading
import time
import uuid
import xml.etree.ElementTree as ET

import paho.mqtt.client as mqtt
import requests

log = logging.getLogger("trc_tally.core")

CONFIG_FILE = "config.json"
COLORSCHEMES_FILE = "ColorSchemes.json"
LEGACY_TALLY_FILE = "tallyAssignments.json"


def resource_path(name):
    """Resolve a bundled read-only asset, whether running from source or a
    PyInstaller one-file build (where assets live under sys._MEIPASS)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)

HTTP_TIMEOUT = 2.0  # seconds; a poll must never block its worker forever
WLED_PORT = 21324
WLED_DRGB_HEADER = bytes.fromhex("0205")  # protocol 2 (DRGB), 5s revert (matches firmware)

# Tally state codes understood by the firmware.
OFF, PROGRAM, PREVIEW, REC, STREAM, PREVIEW_OP, IDENTIFY, IDLE = 0, 1, 2, 3, 4, 5, 9, 10
STATE_LABEL = {
    OFF: "Off", PROGRAM: "Live", PREVIEW: "Preview", REC: "Recording",
    STREAM: "Streaming", PREVIEW_OP: "Preview (op)", IDENTIFY: "Identify", IDLE: "Idle",
}
# Codes a poller may set automatically; everything else is manual-test only.
AUTO_CODES = {OFF, PROGRAM, PREVIEW, PREVIEW_OP}
# ColorSchemes.json scheme ids used for local (UDP) lights.
LOCAL_SCHEME_ID = {OFF: "off", PROGRAM: "live", PREVIEW: "pre", PREVIEW_OP: "pre"}


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
class ConfigStore:
    """Thread-safe load/save of config.json, with one-time v1->v2 migration."""

    def __init__(self, path=CONFIG_FILE):
        self.path = path
        self._lock = threading.RLock()
        self._cfg = self._load_or_migrate()
        self.save()

    # -- loading / migration ------------------------------------------------ #
    def _load_or_migrate(self):
        raw = {}
        if os.path.exists(self.path):
            with open(self.path) as fh:
                raw = json.load(fh)
        if raw.get("version") == 2:
            return self._with_defaults(raw)
        return self._migrate_v1(raw)

    def _with_defaults(self, cfg):
        cfg.setdefault("version", 2)
        cfg.setdefault("web", {})
        cfg["web"].setdefault("port", 8070)
        cfg["web"].setdefault("password", "changeme")
        cfg.setdefault("mqtt", {})
        cfg["mqtt"].setdefault("broker_ip", "10.10.10.190")
        cfg["mqtt"].setdefault("broker_port", 18069)
        cfg.setdefault("machines", [])
        cfg.setdefault("tallies", [])
        return cfg

    def _migrate_v1(self, old):
        """Build v2 from the old config.json (api_urls) + tallyAssignments.json."""
        log.info("Migrating configuration to v2")
        machines = []
        for i, url in enumerate(old.get("api_urls", []) or []):
            if not url or str(url).startswith("[INSERT"):
                continue
            machines.append({
                "id": f"m{i}", "name": f"vMix {i + 1}", "url": url,
                "refresh_ms": old.get("api_refresh", 200),
            })

        tallies = []
        tfile = old.get("tallyfile", LEGACY_TALLY_FILE)
        if os.path.exists(tfile):
            with open(tfile) as fh:
                for j, t in enumerate(json.load(fh)):
                    idx = t.get("apiIndex", 0)
                    mid = machines[idx]["id"] if 0 <= idx < len(machines) else (
                        machines[0]["id"] if machines else None)
                    tallies.append({
                        "id": f"t{j}", "name": t.get("name", f"Tally {j + 1}"),
                        "mac": t.get("mac", ""), "cloud": bool(t.get("cloud", True)),
                        "ip": t.get("ip", ""), "machine_id": mid,
                        "input_id": t.get("inputID", t.get("input_id", 1)),
                        "fullpreview": True,
                    })
            self._backup(tfile)

        if os.path.exists(self.path):
            self._backup(self.path)

        cfg = self._with_defaults({"version": 2, "machines": machines, "tallies": tallies})
        broker = old.get("mqtt_broker_ip")
        if broker and not str(broker).startswith("[INSERT"):
            cfg["mqtt"]["broker_ip"] = broker
        if old.get("mqtt_broker_port"):
            cfg["mqtt"]["broker_port"] = old["mqtt_broker_port"]
        return cfg

    @staticmethod
    def _backup(path):
        bak = path + ".bak"
        try:
            if not os.path.exists(bak):
                with open(path) as src, open(bak, "w") as dst:
                    dst.write(src.read())
                log.info("Backed up %s -> %s", path, bak)
        except OSError as exc:
            log.warning("Could not back up %s: %s", path, exc)

    def save(self):
        with self._lock:
            tmp = self.path + ".tmp"
            with open(tmp, "w") as fh:
                json.dump(self._cfg, fh, indent=2)
            os.replace(tmp, self.path)

    # -- reads -------------------------------------------------------------- #
    def snapshot(self):
        with self._lock:
            return copy.deepcopy(self._cfg)

    @property
    def web(self):
        with self._lock:
            return dict(self._cfg["web"])

    @property
    def mqtt(self):
        with self._lock:
            return dict(self._cfg["mqtt"])

    def machines(self):
        with self._lock:
            return copy.deepcopy(self._cfg["machines"])

    def machine(self, mid):
        with self._lock:
            return next((dict(m) for m in self._cfg["machines"] if m["id"] == mid), None)

    def tallies(self):
        with self._lock:
            return copy.deepcopy(self._cfg["tallies"])

    def tallies_for(self, mid):
        with self._lock:
            return [dict(t) for t in self._cfg["tallies"] if t.get("machine_id") == mid]

    def tally(self, tid):
        with self._lock:
            return next((dict(t) for t in self._cfg["tallies"] if t["id"] == tid), None)

    # -- machine CRUD ------------------------------------------------------- #
    def add_machine(self, data):
        with self._lock:
            mid = "m" + uuid.uuid4().hex[:8]
            machine = {
                "id": mid, "name": data.get("name", "vMix"),
                "url": data.get("url", ""), "refresh_ms": int(data.get("refresh_ms", 200)),
            }
            self._cfg["machines"].append(machine)
            self.save()
            return machine

    def update_machine(self, mid, data):
        with self._lock:
            for m in self._cfg["machines"]:
                if m["id"] == mid:
                    for k in ("name", "url"):
                        if k in data:
                            m[k] = data[k]
                    if "refresh_ms" in data:
                        m["refresh_ms"] = int(data["refresh_ms"])
                    self.save()
                    return dict(m)
            return None

    def delete_machine(self, mid):
        with self._lock:
            self._cfg["machines"] = [m for m in self._cfg["machines"] if m["id"] != mid]
            for t in self._cfg["tallies"]:
                if t.get("machine_id") == mid:
                    t["machine_id"] = None
            self.save()

    # -- tally CRUD --------------------------------------------------------- #
    def add_tally(self, data):
        with self._lock:
            tid = "t" + uuid.uuid4().hex[:8]
            tally = {
                "id": tid, "name": data.get("name", "Tally"),
                "mac": data.get("mac", ""), "cloud": bool(data.get("cloud", True)),
                "ip": data.get("ip", ""), "machine_id": data.get("machine_id"),
                "input_id": int(data.get("input_id", 1)),
                "fullpreview": bool(data.get("fullpreview", True)),
            }
            self._cfg["tallies"].append(tally)
            self.save()
            return tally

    def update_tally(self, tid, data):
        with self._lock:
            for t in self._cfg["tallies"]:
                if t["id"] == tid:
                    for k in ("name", "mac", "ip", "machine_id"):
                        if k in data:
                            t[k] = data[k]
                    if "cloud" in data:
                        t["cloud"] = bool(data["cloud"])
                    if "fullpreview" in data:
                        t["fullpreview"] = bool(data["fullpreview"])
                    if "input_id" in data:
                        t["input_id"] = int(data["input_id"])
                    self.save()
                    return dict(t)
            return None

    def delete_tally(self, tid):
        with self._lock:
            self._cfg["tallies"] = [t for t in self._cfg["tallies"] if t["id"] != tid]
            self.save()

    # -- settings (web + mqtt sections) ------------------------------------- #
    def update_web(self, data):
        with self._lock:
            if str(data.get("port", "")).strip():
                self._cfg["web"]["port"] = int(data["port"])
            if data.get("password"):  # blank = leave unchanged
                self._cfg["web"]["password"] = data["password"]
            self.save()
            return dict(self._cfg["web"])

    def update_mqtt(self, data):
        with self._lock:
            if str(data.get("broker_ip", "")).strip():
                self._cfg["mqtt"]["broker_ip"] = data["broker_ip"].strip()
            if str(data.get("broker_port", "")).strip():
                self._cfg["mqtt"]["broker_port"] = int(data["broker_port"])
            self.save()
            return dict(self._cfg["mqtt"])


# --------------------------------------------------------------------------- #
# Event bus (for SSE) and runtime state
# --------------------------------------------------------------------------- #
class EventBus:
    def __init__(self):
        self._subs = set()
        self._lock = threading.Lock()

    def subscribe(self):
        q = queue.Queue(maxsize=100)
        with self._lock:
            self._subs.add(q)
        return q

    def unsubscribe(self, q):
        with self._lock:
            self._subs.discard(q)

    def publish(self, event):
        with self._lock:
            subs = list(self._subs)
        for q in subs:
            try:
                q.put_nowait(event)
            except queue.Full:
                pass


class RuntimeState:
    """Live per-tally and per-machine status, with change events."""

    def __init__(self, bus):
        self._bus = bus
        self._lock = threading.Lock()
        self._tallies = {}   # tally_id -> {code, label, updated_at}
        self._machines = {}  # machine_id -> {connected, mode, active, preview, last_error}

    def set_mode(self, mid, mode):
        with self._lock:
            m = self._machines.setdefault(mid, {})
            m["mode"] = mode
        self._bus.publish({"type": "machine", "id": mid, **self.machine(mid)})

    def get_mode(self, mid):
        with self._lock:
            return self._machines.get(mid, {}).get("mode", "live")

    def update_machine(self, mid, **fields):
        with self._lock:
            m = self._machines.setdefault(mid, {"mode": "live"})
            m.update(fields)
        self._bus.publish({"type": "machine", "id": mid, **self.machine(mid)})

    def set_tally(self, tid, code):
        with self._lock:
            prev = self._tallies.get(tid, {}).get("code")
            self._tallies[tid] = {
                "code": code, "label": STATE_LABEL.get(code, str(code)),
                "updated_at": time.time(),
            }
            changed = prev != code
        if changed:
            self._bus.publish({"type": "tally", "id": tid, "code": code,
                               "label": STATE_LABEL.get(code, str(code))})

    def machine(self, mid):
        with self._lock:
            m = self._machines.get(mid, {})
            return {"connected": m.get("connected", False), "mode": m.get("mode", "live"),
                    "active": m.get("active"), "preview": m.get("preview"),
                    "last_error": m.get("last_error")}

    def snapshot(self):
        with self._lock:
            return {"tallies": copy.deepcopy(self._tallies),
                    "machines": copy.deepcopy(self._machines)}


# --------------------------------------------------------------------------- #
# MQTT transport
# --------------------------------------------------------------------------- #
class MqttManager:
    def __init__(self, broker_ip, broker_port):
        self._start(broker_ip, broker_port)

    def _start(self, broker_ip, broker_port):
        # paho-mqtt 2.x: callback API version is required, and v2 callbacks take
        # a reason_code + properties.
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._client.on_connect = lambda c, u, flags, rc, props=None: log.info("MQTT connected (%s)", rc)
        self._client.on_disconnect = lambda c, u, flags, rc, props=None: log.warning("MQTT disconnected (%s)", rc)
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._client.connect_async(broker_ip, int(broker_port), keepalive=60)
        self._client.loop_start()

    def publish_state(self, mac, code):
        """Publish a state code to a cloud tally (upper-cased MAC topic, retained)."""
        if mac:
            self._client.publish(mac.upper(), str(int(code)), qos=1, retain=True)

    def reconnect(self, broker_ip, broker_port):
        """Point the client at a new broker (after a settings change)."""
        self.stop()
        self._start(broker_ip, broker_port)

    def stop(self):
        self._client.loop_stop()
        self._client.disconnect()


# --------------------------------------------------------------------------- #
# vMix polling
# --------------------------------------------------------------------------- #
def fetch_vmix(session, url):
    """Return (active, preview) input numbers for a vMix instance, or None on error."""
    resp = session.get(url, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    active = int(root.findtext("active"))
    preview_text = root.findtext("preview")
    preview = int(preview_text) if preview_text not in (None, "") else None
    return active, preview


# --------------------------------------------------------------------------- #
# Serial provisioning (matches the vendor's USB setup protocol)
# --------------------------------------------------------------------------- #
SERIAL_BAUD = 115200


def list_serial_ports():
    try:
        from serial.tools import list_ports
    except ImportError:
        return []
    return [p.device for p in list_ports.comports() if "Bluetooth" not in (p.device or "")]


def _serial_send(port, payload, wait_ack=True, timeout=10):
    try:
        import serial
    except ImportError:
        return {"ok": False, "error": "pyserial not installed"}
    try:
        with serial.Serial(port, SERIAL_BAUD, timeout=1) as ser:
            ser.write(payload.encode())
            if not wait_ack:
                return {"ok": True}
            deadline = time.time() + timeout
            buf = b""
            while time.time() < deadline:
                buf += ser.read(128)
                text = buf.decode(errors="ignore")
                if "#TLYMASETUPMSGOK" in text or "#TLYMASETUPSTOPWIFICONNECT" in text:
                    return {"ok": True}
                if "#TLYMASETUPNOK" in text:
                    return {"ok": False, "error": "Device rejected the configuration"}
            return {"ok": False, "error": "No acknowledgement from device (timeout)"}
    except Exception as exc:  # noqa: BLE001 - surface any serial error to the UI
        return {"ok": False, "error": str(exc)}


def provision_tally(port, s):
    """Send WiFi + cloud config to a tally over USB serial (#TLYMASETUPMSG)."""
    dhcp = "dhcp" if str(s.get("dhcp", "dhcp")) in ("dhcp", "true", "True", "1") else "false"
    payload = json.dumps({
        "cmd": "#TLYMASETUPMSG",
        "ssid": s.get("ssid", ""),
        "pwd": s.get("pwd", ""),
        "dhcp": dhcp,
        "ip": s.get("ip", "0.0.0.0") if dhcp == "false" else "0.0.0.0",
        "subnet": s.get("subnet", "0.0.0.0") if dhcp == "false" else "0.0.0.0",
        "gateway": s.get("gateway", "0.0.0.0") if dhcp == "false" else "0.0.0.0",
        "cloudserver": s.get("cloudserver", ""),
        "cloudport": str(s.get("cloudport", "")),
        "cloudmode": str(s.get("cloudmode", "1")),
    })
    if not payload or not s.get("ssid"):
        return {"ok": False, "error": "SSID is required"}
    return _serial_send(port, payload, wait_ack=True)


def reset_tally(port):
    """Erase a tally's stored config (#TLYMAERASETALLY)."""
    payload = json.dumps({
        "cmd": "#TLYMAERASETALLY", "ssid": "", "pwd": "", "dhcp": "",
        "ip": "", "subnet": "", "gateway": "", "cloudserver": "",
        "cloudport": "", "cloudmode": "0",
    })
    return _serial_send(port, payload, wait_ack=False)


def fetch_vmix_inputs(url):
    """Return the list of inputs from a vMix instance for the picker UI."""
    resp = requests.get(url, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    inputs = []
    for inp in root.findall("./inputs/input"):
        try:
            number = int(inp.get("number"))
        except (TypeError, ValueError):
            continue
        inputs.append({
            "number": number,
            "key": inp.get("key"),
            "title": (inp.get("title") or (inp.text or "").strip()),
            "type": inp.get("type"),
        })
    return inputs


def build_local_payloads(color_schemes):
    """Pre-build the WLED UDP payload for each local tally state."""
    by_id = {s["schemeID"]: s for s in color_schemes}
    payloads = {}
    for code, sid in LOCAL_SCHEME_ID.items():
        scheme = by_id.get(sid)
        if scheme and isinstance(scheme.get("SchemeData"), str):
            payloads[code] = WLED_DRGB_HEADER + bytes.fromhex(scheme["SchemeData"])
    return payloads


def compute_state(active, preview, tally):
    if tally["input_id"] == active:
        return PROGRAM
    if preview is not None and tally["input_id"] == preview:
        return PREVIEW if tally.get("fullpreview", True) else PREVIEW_OP
    return OFF


class PollerWorker(threading.Thread):
    """Polls one vMix machine and drives its assigned tallies. One per machine."""

    def __init__(self, machine_id, core):
        super().__init__(daemon=True, name=f"poller-{machine_id}")
        self.machine_id = machine_id
        self._core = core
        self._stop = threading.Event()
        self._session = requests.Session()
        self._last = {}  # tally_id -> last code sent (for change detection)

    def stop(self):
        self._stop.set()

    def run(self):
        core = self._core
        while not self._stop.is_set():
            machine = core.config.machine(self.machine_id)
            if machine is None:
                return
            refresh = max(machine.get("refresh_ms", 200), 50) / 1000.0

            if core.state.get_mode(self.machine_id) == "manual":
                core.state.update_machine(self.machine_id, connected=True)
                self._stop.wait(refresh)
                continue

            try:
                active, preview = fetch_vmix(self._session, machine["url"])
                core.state.update_machine(self.machine_id, connected=True,
                                          active=active, preview=preview, last_error=None)
            except (requests.RequestException, ET.ParseError, TypeError, ValueError) as exc:
                core.state.update_machine(self.machine_id, connected=False, last_error=str(exc))
                self._stop.wait(refresh)
                continue

            for tally in core.config.tallies_for(self.machine_id):
                code = compute_state(active, preview, tally)
                core.drive_tally(tally, code, self._last)

            self._stop.wait(refresh)


class PollerManager:
    def __init__(self, core):
        self._core = core
        self._workers = {}
        self._lock = threading.Lock()

    def start_all(self):
        for m in self._core.config.machines():
            self.start(m["id"])

    def start(self, mid):
        with self._lock:
            if mid in self._workers and self._workers[mid].is_alive():
                return
            worker = PollerWorker(mid, self._core)
            self._workers[mid] = worker
            worker.start()

    def stop(self, mid):
        with self._lock:
            worker = self._workers.pop(mid, None)
        if worker:
            worker.stop()

    def restart(self, mid):
        self.stop(mid)
        self.start(mid)

    def reconcile(self):
        """Start workers for new machines, stop those for removed ones."""
        current = {m["id"] for m in self._core.config.machines()}
        with self._lock:
            known = set(self._workers)
        for mid in current - known:
            self.start(mid)
        for mid in known - current:
            self.stop(mid)

    def stop_all(self):
        with self._lock:
            workers = list(self._workers.values())
            self._workers.clear()
        for w in workers:
            w.stop()


# --------------------------------------------------------------------------- #
# Core facade
# --------------------------------------------------------------------------- #
class Core:
    def __init__(self):
        self.config = ConfigStore()
        self.bus = EventBus()
        self.state = RuntimeState(self.bus)
        mqtt_cfg = self.config.mqtt
        self.mqtt = MqttManager(mqtt_cfg["broker_ip"], mqtt_cfg["broker_port"])
        self.local_payloads = self._load_local_payloads()
        self._udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.pollers = PollerManager(self)
        # Seed machine modes so the UI shows "live" immediately.
        for m in self.config.machines():
            self.state.update_machine(m["id"], connected=False)

    @staticmethod
    def _load_local_payloads():
        # Prefer a user copy in the working dir; fall back to the bundled asset.
        path = COLORSCHEMES_FILE if os.path.exists(COLORSCHEMES_FILE) else resource_path(COLORSCHEMES_FILE)
        if os.path.exists(path):
            try:
                with open(path) as fh:
                    return build_local_payloads(json.load(fh))
            except (json.JSONDecodeError, ValueError) as exc:
                log.warning("Could not load %s: %s", path, exc)
        return {}

    def drive_tally(self, tally, code, last_cache=None):
        """Send a state to a tally over its transport and record runtime state."""
        if tally["cloud"]:
            changed = last_cache is None or last_cache.get(tally["id"]) != code
            if changed:
                self.mqtt.publish_state(tally["mac"], code)
        else:
            payload = self.local_payloads.get(code) or self.local_payloads.get(OFF)
            if payload and tally.get("ip"):
                try:
                    self._udp.sendto(payload, (tally["ip"], WLED_PORT))
                except OSError as exc:
                    log.error("UDP send to %s failed: %s", tally["ip"], exc)
        if last_cache is not None:
            last_cache[tally["id"]] = code
        self.state.set_tally(tally["id"], code)

    def send_command(self, tally, code):
        """Manual test command (bypasses change-detection so it always fires)."""
        self.drive_tally(tally, code, None)

    def shutdown(self):
        self.pollers.stop_all()
        for t in self.config.tallies():
            if t["cloud"]:
                self.mqtt.publish_state(t["mac"], OFF)
        self.mqtt.stop()
