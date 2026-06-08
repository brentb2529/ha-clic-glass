# Cardinal CLiC Privacy Glass — Home Assistant custom integration

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![HA Quality Scale: Bronze](https://img.shields.io/badge/Quality%20Scale-Bronze-cd7f32.svg)](custom_components/clic/quality_scale.yaml)

Local-polling integration for the **Cardinal CLiC HC-108 Network Controller**.
Talks to the HC-108's on-board LAN REST API (the "Fog Layer" API) to deliver
**real per-channel glass state** (Clear/Private) plus command control, the
global privacy override, and per-channel fault/lockout diagnostic telemetry
— no optimistic state, no cloud, no relay hardware required.

---

## Supported hardware

| Model | Type | Supported | Notes |
|---|---|---|---|
| **HC-108** | 8-channel network controller | **Yes — primary target** | LAN REST API (Fog Layer); this integration |
| HC-198 | 8-channel standalone controller | No | Dry-contact only; no network API |
| WC-101 | Single-channel wall controller | No | No network port |
| WD-02.1.x / WD-02.2 | Single-panel glass controllers | No | No network port |

This integration targets the **HC-108** exclusively. For the non-networked
controllers (HC-198, WC-101, WD-02.x) use a Lutron / Shelly / ESPHome
relay to drive the dry-contact trigger input and represent it as a standard
`switch` entity in HA — no custom integration needed.

---

## API confidence note

The HC-108 **data model** (per-channel GLASS OUT STATUS, CHANGE OUTPUT,
LOCKOUT STATUS, TRIGGER STATUS, GLOBAL STATUS, and Global Override) is
**confirmed** from the HC-108 Rev. A Installation Manual, Internal Webpage
section.

The exact **REST route strings** are **assumed** — the HC-108 serves its own
"API Routes Specifications" and "Python API SDK" pages at runtime (accessible
on the device's "Links" page), but these are not published publicly. All route
constants are isolated in `custom_components/clic/api.py` and can be corrected
in one place once read off a real HC-108. The integration attempts a
best-effort `async_discover_routes()` call at setup to self-correct.

Default web UI credentials: **admin / admin** (documented in the manual).

---

## Install & Setup

Everything is done through the Home Assistant UI — no YAML editing, no
configuration files, no manual entry IDs required.

### Step 1 — Install the integration

**Via HACS (recommended)**

1. Open HACS in Home Assistant.
2. Click the three-dot menu → **Custom repositories**.
3. Paste this repository URL, category **Integration**, and click **Add**.
4. Search for "Cardinal CLiC" and click **Download**.
5. Restart Home Assistant.

**Manual install**

1. Copy the `custom_components/clic/` folder to
   `<your HA config>/custom_components/clic/`.
2. Restart Home Assistant.

---

### Step 2 — Add the HC-108 controller

1. Go to **Settings → Devices & Services** and click **Add Integration**.
2. Search for **Cardinal CLiC** and click it.
3. Enter your HC-108's **IP address or hostname** (find it on the controller's
   front-panel Settings tab, or your router's DHCP table).
   - Port: leave at **80** unless you've changed it.
   - Auth fields (username, password, API token) are **optional** — leave them
     blank first. If the controller is password-protected, the default
     credentials are **admin / admin**.
4. Click **Submit**. The integration connects to the controller and detects
   how many glass channels are installed.
5. **Name your glass zones.** Give each channel a friendly name
   (e.g. "Master Bath", "Office Partition"). These become the device names in
   Home Assistant. You can rename them at any time later.
6. Click **Submit**. Done.

The integration creates one hub device for the HC-108 controller and one
child device for each glass zone.

**Multiple HC-108 controllers** are fully supported — repeat the steps above
for each controller. Each entry is identified by the controller's MAC address
so there are no conflicts.

---

### Tip — give your controller a static IP

The HC-108 does not announce itself on the network; you must enter its IP
address manually. To avoid the IP changing after a router reboot, either:
- Set a **DHCP reservation** on your router (bind the HC-108's MAC address to
  a fixed IP), or
- Assign a **static IP** on the HC-108 itself from its built-in web UI.

The HC-108's MAC address is shown on its front-panel Settings tab and in the
Home Assistant device registry after setup.

---

### Changing settings after setup

| What you want to do | How |
|---|---|
| Rename glass zones | **Settings → Devices & Services → Cardinal CLiC → Configure** |
| Change host/port or credentials | Three-dot menu on the integration entry → **Reconfigure** |
| Fix an auth error banner | Click the banner → re-enter credentials |
| Remove the integration | Three-dot menu → **Delete** |

---

## Discovery

The HC-108 does not broadcast mDNS/zeroconf or SSDP announcements — it is
a plain LAN device that acquires a DHCP or static IP. Configure a **static
IP** (or DHCP reservation by MAC) on your router so the address is stable.
The HC-108 MAC address is shown on its front-panel Settings tab and is used
as the unique ID in HA.

---

## Entities

### Per controller (hub device: "CLiC HC-108")

| Entity | Platform | Description |
|---|---|---|
| `switch.<name>_all_glass_private` | Switch (CONFIG) | **Global Override.** ON forces all panels to the controller's configured target (default **Private**) and blocks all trigger inputs. Useful for alarm/scene "all private" actions. |

### Per glass channel/zone (child device per channel)

| Entity | Platform | Description |
|---|---|---|
| `switch.<zone_name>` | Switch | **ON = Clear, OFF = Private.** State is the ACTUAL glass output (GLASS OUT STATUS) from the API — not optimistic. |
| `binary_sensor.<zone_name>_fault` | Binary Sensor (PROBLEM, DIAGNOSTIC) | **On = fault.** Actual glass state does not match the requested state — indicates a wiring error or missing panel. |
| `binary_sensor.<zone_name>_lockout` | Binary Sensor (LOCK, DIAGNOSTIC) | **On = locked.** The Local Lockout dry-contact input is active, preventing the channel from going Clear. Read-only (hardware input). |

### State semantics

- **ON = Clear** (glass is transparent), **OFF = Private** (glass is opaque).
- CLiC failsafe: glass goes **Private** when unpowered or trigger is open.
  HA "off" / unavailable aligns with this privacy-safe default.
- The LOCK/fault binary sensors are diagnostic and appear in the entity details,
  not the main device card.

---

## Options

After setup, click **Configure** on the integration entry to rename glass zones.
Changes take effect immediately (the entry reloads).

### Reconfiguring the connection

To update the HC-108's IP address, port, or credentials without removing the
integration (preserving your entity history and automations), use
**three-dot menu → Reconfigure** on the integration entry.

### Reauthentication

If the HC-108 starts rejecting credentials, Home Assistant will show a
notification banner. Click the banner to open the reauth form — you can
update credentials there without re-adding the integration.

---

## Removing the integration

Go to **Settings → Devices & Services**, find "Cardinal CLiC Privacy Glass",
click the three-dot menu, and select **Delete**. All entities and devices are
removed. The HC-108 hardware is unaffected.

---

## Development

```bash
cd clic-glass/
python3 -m venv .venv
.venv/bin/pip install pytest-homeassistant-custom-component
.venv/bin/python -m pytest tests/ -v      # run the test suite
.venv/bin/python -m fake.server           # run the fake HC-108 (127.0.0.1:8108)
```

### Updating API routes

If you have access to a real HC-108:

1. Browse to `http://<HC-108-IP>/` and log in (admin / admin).
2. Navigate to the **Links** page.
3. Open **API Routes Specifications** — this is the live Fog Layer API spec.
4. Update `PATH_*` constants in `custom_components/clic/api.py` and the
   matching routes in `fake/server.py`.

---

## Known limitations and hardware-verification items

- REST route strings are **assumed** (see API confidence note above). All
  state-machine logic is correct; only the HTTP paths need verification once
  access to a real HC-108 is available.
- Auth model: the integration supports Bearer token and HTTP Basic Auth. The
  exact scheme used by the Fog Layer API is unconfirmed; try without auth first
  (default admin / admin if credentials are required).
- No mDNS/zeroconf auto-discovery (HC-108 does not announce itself on the
  network — manual IP entry required).
- Route self-discovery (`async_discover_routes`) is best-effort; it logs a
  debug message on failure and does not affect integration operation.
