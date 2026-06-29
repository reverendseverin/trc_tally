# TRC Tally

A vMix tally-light controller with a web management interface. It polls one or
more vMix instances over the HTTP API and drives physical tally lights to show
which camera input is **live** (red) or in **preview** (green).

Two kinds of lights are supported:

| Light type | Transport | Payload |
|------------|-----------|---------|
| **Cloud**  | MQTT      | state code on topic `<MAC>` (upper-cased), retained |
| **Local**  | UDP       | WLED realtime (DRGB) packet to `<ip>:21324` |

## Running

```bash
pip install -r requirements.txt
python TRC_Tally_Cloud_Client.py
```

Then open **http://localhost:8070** and sign in (default password `changeme` —
change `web.password` in `config.json`). Everything is managed from the browser:

- **Dashboard** — every tally drawn as the real device, lit by its live state.
- **Machines & assignments** — add vMix machines, **drag tallies onto them**,
  and per machine: a **Live/Manual** toggle, a **Restart** button (recovers a
  frozen poller without restarting the whole app), and edit/delete.
- **Test commands** — flip a machine to **Manual** (its poller pauses) and send
  any state to its tallies, including **Identify** (flash to locate a light).

Build a standalone executable: `pyinstaller TRC_Tally_Cloud_Client.spec`.

## Cloud tally state codes

| Code | Meaning | Light |
|------|---------|-------|
| 0 | Off | LEDs off |
| 1 | Program / live | Solid red |
| 2 | Preview | Solid green |
| 3 | Recording | Animated red |
| 4 | Streaming | Animated magenta |
| 5 | Preview, operator-only | Green on operator side only |
| 9 | Identify | Flashes to locate the device |
| 10 | Idle / standby | Solid white |

Auto-polling drives `0/1/2` (and `5` when a tally's *full preview* is off). The
rest are available as manual test commands.

## Testing without vMix

`vmixemulator.py` serves a fake vMix XML API and lets you type new
`preview`/`active` input numbers on the console. Run one per machine:

```bash
python vmixemulator.py 8101    # first instance
python vmixemulator.py 8102    # second instance (new terminal)
```

Add machines in the UI pointing at `http://127.0.0.1:8101` etc.

## Configuration

Config lives in `config.json` (schema v2) and is edited through the UI — you
shouldn't need to touch it by hand. An older `config.json` + `tallyAssignments.json`
is migrated automatically on first run (originals saved as `*.bak`).

```json
{
  "version": 2,
  "web":   { "port": 8070, "password": "changeme" },
  "mqtt":  { "broker_ip": "10.10.10.190", "broker_port": 18069 },
  "machines": [
    { "id": "m1", "name": "Main vMix", "url": "http://10.0.0.5:8088", "refresh_ms": 200 }
  ],
  "tallies": [
    { "id": "t1", "name": "Cam 1", "mac": "AC:0B:FB:D7:EC:B0",
      "cloud": true, "ip": "", "machine_id": "m1", "input_id": 1, "fullpreview": true }
  ]
}
```

- `machines[].url` — a vMix HTTP API endpoint. `refresh_ms` — poll interval.
- `tallies[].machine_id` — which machine this tally follows.
- `tallies[].input_id` — the vMix **input number** this light represents.
- `tallies[].cloud` — `true` = MQTT (needs `mac`); `false` = UDP (needs `ip`).

`ColorSchemes.json` defines the colours used for local (UDP) lights.
