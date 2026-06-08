# Cardinal CLiC Privacy Glass — Home Assistant custom integration

Local-polling integration for the **Cardinal CLiC HC-108 Network Controller**,
talking to its on-board LAN REST API (the "Fog Layer" API). Gives **real
per-channel glass state** (Clear/Private) plus control, the global override,
and per-channel fault/lockout telemetry — no optimistic state, no cloud.

> Status: built + tested standalone against the bundled fake HC-108 server.
> NOT yet wired into the dev HA stack (coordinator does that). New repo —
> awaiting coordinator sign-off before any GitHub remote.

## Entities

Per controller (hub device "CLiC HC-108"):
- `switch.<...>_all_glass_private` — Global Override. ON forces all panels to
  the controller's configured target (default **Private**); blocks triggers.

Per channel / glass zone (one device each, `via_device` the hub):
- `switch.clic_glass_<n>` — **ON = Clear, OFF = Private**, real state from
  GLASS OUT STATUS.
- `binary_sensor` PROBLEM — channel fault (actual state != requested state;
  e.g. external wiring error / missing panel).
- `binary_sensor` LOCK — Local Lockout input, read-only (on = unlocked).

## API confidence

The HC-108 **data model** is confirmed from the HC-108 Rev. A manual (Internal
Webpage → Hardware page). The exact **REST route strings** are **assumed**: the
device serves its own "API Routes Specifications" + "Python API SDK" pages at
runtime, and these are not published publicly. The route paths are isolated as
constants in `custom_components/clic/api.py` (and mirrored in `fake/server.py`)
so they can be corrected in one place once read off a real HC-108.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install pytest-homeassistant-custom-component
.venv/bin/python -m pytest tests/ -q          # run the test suite
.venv/bin/python -m fake.server               # run the fake HC-108 (127.0.0.1:8108)
```
