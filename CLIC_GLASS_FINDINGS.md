# CLiC Glass Control — FIND Step Findings

Module: **Clic Glass control** (smart/switchable privacy glass, Bensten residence)
Step: **FIND** (research-first). Owner: CLIC GLASS expert.
Policy: control wiring is **EQUIPMENT-ACTUATING (low hazard)** → recommend + flag for human approval; lead with state/telemetry. Never PR to HA core; forks only if code is needed.
Status: research complete; **classification = Modbus/generic-local (relay-driven `switch`), no custom code expected.** Pending physical/wiring details from user (see section E).

---

## (a) Product identification + confidence + citations

**Identified product: CLiC Smart Privacy Glass — by Cardinal IG / Cardinal Glass Industries (Cardinal IG Company).**
Confidence: **High (~0.9)** that the residence's "Clic Glass" is this product. The coordinator independently confirmed the brand and the official site (clicglass.com).

- **Technology: PSCT — Polymer-Stabilized Cholesteric Texture liquid crystal**, applied direct-to-glass. This is Cardinal's specific LC variant; it is NOT classic PDLC, NOT electrochromic, NOT SPD. Marketing: "patented direct-to-glass PSCT liquid crystal technology," "haze-free views," switches in <100 ms / "milliseconds."
- **Behavior: binary** — two discrete states only, **Clear** and **Private**. PSCT is switched between transparent and opaque states by voltage pulses; it is **not a dimmable/0-100% opacity** technology. (Some PSCT variants are bistable, but the CLiC *controller* drives a maintained state — see (b).)
- Power: NEC **Class 3 power-limited low-voltage** system; "less than 1/2 watt per square foot when active in the clear state," "less than a 25W lightbulb for an 8x5 ft pane."

> Correction to a working hypothesis: the FAQ "what happens on power loss" question led to a guess that this is PDLC (clear-when-powered). The controller manuals show the **opposite**: CLiC's failsafe is **Private** when the trigger is open / on power loss (see (b)). So do NOT assume PDLC clear-on-power semantics.

Citations:
- https://www.clicglass.com/ (product, "smart privacy glass," integrates with smart home)
- https://www.clicglass.com/technology/ (PSCT, Class 3 low voltage, third-party control)
- https://www.cardinalcorp.com/glossary/switchable-privacy-glass/ (Cardinal as manufacturer; PSCT)
- https://www.dwell.com/article/switchable-smart-glass-next-generation-of-privacy-clic-53cdfa84 (binary clear/private, "touch of a button," milliseconds)
- https://www.usglassmag.com/next-generation-switchable-privacy-glass/ (Cardinal CLiC overview)
- https://cascoonline.com/clic (controller model list: WC-101 single-channel; HC-198 / HC-108 multi-channel; "basic light switch (unpowered), smart device, or building management system")

---

## (b) Control interface + state feedback

**The controller is the integration point, not the glass.** CLiC ships with a proprietary Cardinal controller; the glass is dumb (a capacitive AC load). Documented controller models:

- **WC-101** — single-channel wall controller
- **HC-108 / HC-198** — multi-channel standalone controllers (HC-198 = up to **8 independent glass outputs**)
- **WD-02.x** family (WD-02.1.3 / WD-02.1.4 / WD-02.2) — glass controllers (older/companion line)

**HC-198 standalone controller — definitive specs (from the manual):**
- **AC glass output:** "75VAC Max, 1.1 Amps, Capacitive Load, Class 3 AC Voltage Power Output." (The controller generates the AC drive waveform for the LC; you do not switch line voltage to the glass directly.)
- **Channels:** up to **8 glass outputs**, each operating independently.
- **Trigger Input Circuit** ("custom engineered") — accepts "switch devices, relays, contact closures, or other automation controllers." Two equivalent ways to command each channel:
  - **Dry contact:** glass goes **Clear** when the contact is **shorted to ground**; goes **Private** when the contact is **open**.
  - **Voltage trigger:** **Clear** when input **> +2.8 VDC**; **Private** when **< +2.4 VDC**; **max input +25 VDC**. Input trigger type: **open collector**.
  - Multiple channels' trigger inputs can be **paralleled** so one switch drives several glass zones.
- **Wiring:** min **18 AWG CL3**; max run controller→glass **328 ft / 100 m**.
- **State model: ON/OFF only** — manual refers to "Glass State is Clear" / "Glass State is Private." **No dimming, no stepped opacity, no brightness.**
- **Failsafe / power-loss default: PRIVATE.** Open trigger = Private; loss of trigger/power → Private (privacy-preserving failsafe).

**State feedback: NONE documented.** The controller exposes a *command input* (dry contact / voltage trigger), not a status output. There is no documented relay/contact/serial line that reports back "currently Clear/Private." → In HA, state will be **inferred** (optimistic / assumed), not read from the device.

**No documented digital protocol** (no RS-232/RS-485/Modbus/0-10V dimming/RF/cloud API found on Cardinal CLiC controllers). Integration is via **contact closure / voltage trigger only**. No published Control4 / Crestron / Lutron / Savant driver was found; Cardinal positions CLiC as compatible with "most building control systems" precisely because the interface is a generic dry contact — any system that can close a relay can drive it.

Citations:
- https://www.manualslib.com/manual/3374622/Cardinal-Clic-Hc-198.html (HC-198 manual mirror — 75VAC/1.1A, 8 outputs, open-collector trigger, Clear/Private states)
- https://www.clicglass.com/wp-content/uploads/2025/03/HC-198-Manual-Rev-B.pdf (HC-198 Rev B — original; trigger thresholds, dry-contact-to-ground → Clear, open → Private, 18 AWG CL3, 328 ft)
- https://www.clicglass.com/wp-content/uploads/WD2_2_Manual-rev-G-1.pdf (WD-02.2 controller manual)
- https://www.clicglass.com/wp-content/uploads/WD2_1_3-Addendum-Rev-A-1.pdf , https://www.clicglass.com/wp-content/uploads/WD2_1_4_Manual-rev-A.pdf (WD-02.1.x)
- https://www.clicglass.com/wp-content/uploads/CLC-SPC-6008-CLiC-Monolithic-3-Part-Specification.pdf (3-part architectural spec)
- https://www.clicglass.com/resources , https://www.clicglass.com/downloads/ (resource index)

> Note: clicglass.com is served behind a WAF (Vercel edge) that 403s scripted PDF fetches and the FAQ answers are JS-rendered, so the manual specs above were corroborated via the ManualsLib mirror and search-index snippets of the official PDFs. Numbers should be re-verified against the actual PDF/installer once we know which controller model is installed.

---

## (c) Existing HA support + recommended path + classification

**Existing HA / HACS support: NONE.** There is no Cardinal CLiC core integration, no HACS custom integration, and no community blueprint/driver for CLiC. (Expected — the device speaks "dry contact," not a network protocol.)

**CLASSIFICATION: Modbus/generic-local — specifically, a relay-driven `switch` (or `light`). NO CUSTOM CODE.**

Reasoning: the controller's command input is a **dry contact / open-collector voltage trigger**. The idiomatic HA path is to drive that contact with a smart relay HA already supports, then represent it as a `switch`:

- **Recommended:** a **Shelly** relay (e.g. Shelly Plus 1 / Pro 1 — *dry-contact / potential-free* variant) wired across the controller's trigger input ↔ ground. Shelly is first-class in HA core (local push, `switch` entity, no cloud). One relay channel per glass zone; HC-198 supports up to 8 zones, so 8 relay channels (or a multi-channel relay board).
  - Wiring sense: relay **closed → trigger shorted to ground → Clear**; relay **open → Private**. (Per policy this wiring is the equipment-actuating part → must be human-approved/installed.)
- **Alternatives** (pick to match what's actually installed):
  - **KNX / Control4 / Lutron / Crestron** already in the home: if the residence has one of these closing the contacts today, bridge via that system's existing HA integration (KNX is core; Control4/Lutron/Crestron via their HA integrations or an intermediate relay).
  - **ESPHome** relay board (GPIO → relay/transistor to ground) if we want a fully local, owned device — also `switch`/`light` with no custom HA code.
  - **Modbus** only if a Modbus relay/IO module is what's wired — `modbus` switch platform, still no custom code.
- **Not applicable:** `light` with brightness, `number` tint level, 0-10V dimmer — the glass is **binary**, so do not model a dimmable surface.
- **State feedback:** none from the glass → use the relay's own reported state as the source of truth (Shelly reports its relay state locally). Model the HA entity **optimistically** off the relay; do not claim to read glass opacity.

**Failsafe nuance for HA modeling:** because open/unpowered = **Private**, "off" should map to **Private** and "on" to **Clear** (relay energized/closed = Clear). Make the HA entity's ON state = Clear so that HA "off"/unknown aligns with the device failsafe (Private).

No HA-core PR is needed and none is warranted (per standing policy). If we later want a friendlier abstraction, it would be a tiny **`b_panels`/template** wrapper in our own repo — not a new integration.

---

## (d) PROPOSED b-panels Glass contract surface

Per-zone (the HC-198 supports up to 8 independent zones; replicate per glass zone). **All control rows are EQUIPMENT-GATED (low hazard) and bind only after the coordinator LOCKs them.** These are PROPOSED only.

| Proposed entity | Platform | Semantics | Gating |
|---|---|---|---|
| `switch.glass_<zone>` (e.g. `switch.glass_master_bath`) | `switch` (Shelly/ESPHome/KNX relay) | **ON = Clear, OFF = Private.** turn_on→close trigger→Clear; turn_off→open→Private | **Equipment-gated (control)** |
| `binary_sensor.glass_<zone>_clear` (optional) | `binary_sensor` | Derived/optimistic Clear-vs-Private indicator (mirrors relay state; not real glass feedback) | Display-only |
| `sensor.glass_<zone>_controller` (optional) | `sensor` / availability | Controller/relay reachability, last command, availability | Display-only (telemetry) |

Surface recommendation for b-panels:
- Render a **toggle tile** (Clear/Private), NOT a slider/dimmer (no opacity levels).
- **Lead with state/telemetry**: show current assumed state + relay availability; make the actual toggle the equipment-gated control that requires approval to wire and (optionally) a UI confirm.
- If multiple zones share one switch wall-control today, expose a **group/scene** as well, but keep per-zone entities as the primitives.
- Do NOT model brightness, tint %, or a `cover`-style position — none map to PSCT binary glass. (`switch` is the correct domain; `light` only if the user explicitly wants it grouped with lighting and accepts on/off-only.)

No row is LOCKED. b-panels must not bind until the coordinator transitions these PROPOSED rows to LOCKED after the relay/entity exists and the gate confirms it.

---

## (e) WHAT WE NEED FROM THE USER (ask once)

Concrete, so the coordinator can collect in a single pass:

1. **Confirm product/tech:** Is the glass **Cardinal CLiC** (clicglass.com)? Any sticker/model on the panels or controller?
2. **Controller model:** Which CLiC controller is installed — **WC-101**, **HC-108**, **HC-198**, or a **WD-02.x**? (Photo of the controller + its label/manual is ideal.) This determines channel count and trigger spec.
3. **How is it driven today?** A plain wall switch? A home-automation system (Control4 / Crestron / Lutron / KNX / Savant)? Nothing yet? If a system already closes the contacts, which one — we can bridge through its existing HA integration.
4. **Wiring access:** Is the controller's **trigger input** terminal accessible (dry contact / voltage-trigger terminals), and is there a spot to add a relay (Shelly/ESPHome) at the controller? Where does the controller live (ceiling void, panel, niche)?
5. **On/off vs dimmable — confirm:** We believe it is **binary Clear/Private only (no dimming)**. Confirm there is no opacity-level control on the existing wall control.
6. **Number of glass zones:** How many independently controllable CLiC panels/zones are there (e.g., master bath, office partition)? Are any ganged to a single switch today?
7. **Failsafe expectation:** Confirm the desired behavior — device default is **Private on power loss / open contact**. Is that the intended privacy failsafe? (Drives how we map HA on/off.)
8. **Docs:** Any installer packet, the controller manual/spec sheet, or wiring diagram from the integrator (the clicglass.com PDFs are WAF-gated; the installed paperwork is authoritative).

---

## Open verification items (for IMPLEMENT step)
- Pull the **actual** controller manual PDF for the installed model (WAF blocked scripted fetch; use a browser or installer copy) to confirm exact trigger thresholds and whether that model has any status/telemetry contact.
- Confirm whether any installed automation system already exposes the glass (avoid double-driving the trigger).
- Choose the relay device (Shelly **dry-contact** model vs ESPHome) based on access and the user's owned-vs-cloud preference (recommend local-only).

> NOTE: Sections (d) and (e) above are the original FIND-era proposal (generic relay path). They are **SUPERSEDED by the FINALIZED DESIGN below.** The decision is to drive the CLiC dry contacts via **Lutron HomeWorks QSX contact-closure (CCO) outputs** through the existing `lutron_caseta` integration — no new relay hardware, no custom code. Both controller manuals (HC-108, WD-02.1.4) have now been read in full; the design below reflects them.

---
---

# FINALIZED DESIGN — Lutron QSX CCO → CLiC (DECISION LOCKED)

Decision (coordinator): **HA drives the CLiC dry contacts via Lutron HomeWorks QSX contact-closure (CCO) outputs, surfaced through the existing `lutron_caseta` integration.** No new relay hardware, no custom code. New install, **3–4 glass zones**, a **MIX of Cardinal controllers** (HC-108 network controller + WD-02.1.4 single-panel controllers).

Standing policy reminder: each CCO→CLiC control path is **EQUIPMENT-ACTUATING (low hazard)** → recommend + flag for human approval; lead with state/telemetry. The Lutron CCO wiring and QSX programming are integrator tasks requiring sign-off.

## 1. Controller manuals — confirmed facts (read in full)

Both manuals confirm the same trigger semantics and the same wiring rule we need. Key confirmed facts:

### WD-02.1.4 Glass Controller (single panel each) — CONFIRMED
- **One CLiC panel per controller.** Terminals "Glass Out A" and "Glass Out B" **both** connect to the **same single** CLiC panel ("Only connect a single CLiC Glass panel. Multiple controllers must be used for multiple CLiC Glass panels."). A and B are NOT two independent outputs — they are the two leads of one panel.
- **Dry Contact In** + **Ground** terminal pair. "The triggering device shall use a **ground referenced switch or relay type output**." **CLOSED = Clear, OPEN = Private.** "There shall be **no power applied directly to the Dry Contact connections**." (i.e., a true **dry** contact.)
- Input Trigger Type: **Open Collector; Shunt to Ground.**
- Powered by its own included 24VDC Class-2 supply (one supply per WD-02.1.4; do not share).
- **No network port, no API, no state feedback.** State is observable only via on-unit Blue/Green LEDs (Green solid = clear, Green off = private, Green flashing = glass wiring fault). → For these zones HA state is **optimistic only** (mirror the Lutron CCO output state).
- Dry contact + glass runs extendable to **100 m / 328 ft**, min **18 AWG**.

### HC-108 Network Controller (multi-channel) — CONFIRMED + NEW CAPABILITY
- **8 independent glass output channels.** Each channel has its own **TRIG / GND / GND / LOCK** 4-position connector and its own **CLiC GLASS OUT** 2-position connector. "Each Glass Out operates independently."
- Per-channel **TRIG SEL** DIP: **Left = Dry Contact mode**, Right = DC Voltage mode. **Set to Dry Contact for Lutron CCO.** (Change only with controller powered off.) **Do not apply voltage to TRIG when in dry-contact mode.**
- **CLOSED (TRIG shunted to GND) = Clear; OPEN = Private** — same sense as WD-02.1.4.
- Up to **4 panels combined per channel** (≤40 sq ft total) but then only controllable as a group — for the residence assume **1 panel per channel** unless the integrator ganged a partition.
- **LOCK (Local Lockout) input** per channel (dry contact): when closed, **disables switching that channel to Clear** — a hardware privacy lock. Available as a safety primitive (not required for the basic toggle).
- **Global Override** input (dry contact): when closed, forces **all** panels to the webpage-configured state (**default Private**) — ideal for an all-private/alarm action. Overrides every trigger and the API.
- **NEW: HC-108 has a LAN port + REST API ("Fog Layer API") + Python SDK**, and an internal webpage exposing per-channel **Glass Out Status** (actual output: 0=private/1=clear) plus Trigger/Lockout/Global status and a direct on/off toggle. This means the HC-108 **could** provide true state feedback and direct control over IP — **but that is NOT the chosen path** (decision is Lutron CCO). Recorded as an option for the IMPLEMENT step if real glass-state feedback is later wanted for the HC-108 zones; would require a small custom/REST integration in our fork, so out of scope now.
- Glass output spec: 75VAC max, 1.1A, capacitive, NEC Class 3. Trigger runs extendable to 100 m / 328 ft, **18 AWG CL3**.

**Shared semantics (both controllers, locked):**
> **Dry contact CLOSED (shunt-to-ground) = CLEAR. Dry contact OPEN = PRIVATE.** Ground-referenced. No voltage on the contact. The state must be **MAINTAINED** (held closed = stays clear; held open = stays private) — it is a level, not a pulse.

## 2. Wiring design — Lutron QSX CCO → CLiC (3–4 zones)

**General rule (applies to every zone):** one **maintained, dry (potential-free)** QSX CCO output per glass zone, wired across that zone's controller **Dry Contact In ↔ Ground** (HC-108: **TRIG ↔ GND**). The CCO contact shorts TRIG/Dry-Contact-In to the controller's own ground reference. **No voltage** from the Lutron side onto the CLiC contact (CLiC provides the sense current; the CCO is just a clean closure). Keep each run within **100 m / 328 ft** at **≥18 AWG** (CL3, CL3P if in plenum).

Per the manuals' own "Multiple channels with automation control / Automation and Relay Controls" diagrams, an automation controller's relay/contact-closure outputs wired to the trigger inputs is an explicitly supported configuration — the Lutron CCO is exactly such a device.

**CCO output configuration (critical):** each CCO output used MUST be programmed in the QSX designer as **MAINTAINED** (latching), **normally-open (NO)**. Do NOT use **momentary/pulsed** mode — a pulse would not hold the CLiC state. NO + maintained means: CCO commanded ON → contact closes → held closed → **Clear**; CCO OFF → contact opens → **Private**. This aligns Lutron "on" with CLiC "clear" and Lutron "off"/power-loss with CLiC "private" (matching CLiC's own private failsafe).

**Mapping for the mixed controller fleet:**

| Zone type | Controller | Channels per controller | CCO outputs needed | Wiring |
|---|---|---|---|---|
| Single-panel zone | **WD-02.1.4** (one per panel) | 1 (one panel only) | **1 CCO output** | CCO → `Dry Contact In` + `Ground` on that WD-02.1.4 |
| Multi-panel / multiple zones on one box | **HC-108** | up to 8 independent | **1 CCO output per channel/zone used** | each CCO → that channel's `TRIG` + `GND` (TRIG SEL = Dry Contact) |

- A zone on a **WD-02.1.4** = exactly **1 CCO output**.
- A zone on the **HC-108** = **1 CCO output per channel** (each channel independent; do not parallel unless intentionally ganging panels into one zone).
- So for **N glass zones, you need N maintained NO CCO outputs**, regardless of the controller mix (3 zones → 3 CCO outputs; 4 zones → 4). If any HC-108 channel ganged multiple panels into a single "zone," that is still 1 CCO output but it switches all ganged panels together.
- **Optional extras (HC-108 only, future):** a CCO output to **Global Override** = "all glass private" emergency/scene action; a CCO output to a channel's **LOCK** = hardware lockout preventing that zone from going clear. Both are equipment-gated and optional; not part of the base per-zone toggle.

## 3. HA mapping

- **The CLiC zone IS the `lutron_caseta` switch entity for its CCO output.** There is no separate CLiC integration and no custom code: HA already owns the QSX processor via `lutron_caseta`, and a maintained switchable Lutron output surfaces as a **`switch.<name>`** entity (entity_id derived from the name programmed in the Lutron app/designer — e.g. a CCO named "Master Bath Glass" → `switch.master_bath_glass`).
  - Source: Home Assistant `lutron_caseta` integration — supports **HomeWorks QSX (not QS)**; switchable loads appear as `switch.<app_name>`. https://www.home-assistant.io/integrations/lutron_caseta/
- **Identify/label the glass zones:** name the CCO outputs in the QSX designer with a clear glass convention (e.g. "Glass – Master Bath", "Glass – Office Partition") so they import as obvious `switch.glass_*` entities. In HA, place them in the correct **Area** (room) and give them a **friendly name** "<Room> Glass"; do not rely on auto-generated names alone. (Recommend an `entity_id` like `switch.glass_<zone>` — rename in HA after import if the Lutron name differs.)
- **State semantics:** **ON = CCO closed = CLEAR; OFF = CCO open = PRIVATE.** `switch.turn_on` → clear, `switch.turn_off` → private. This keeps HA "off"/unknown and any power-loss aligned with CLiC's **Private** failsafe.
- **State is OPTIMISTIC.** The CLiC glass gives **no feedback** on the chosen CCO path (WD-02.1.4 has none at all; HC-108 has feedback only via its own LAN/API, which we are not using here). HA's source of truth is the **Lutron CCO output's own reported state** (the processor reports the CCO commanded state back over LEAP). That tells you what HA/Lutron *commanded*, not a glass sensor — treat it as commanded/assumed state, and do not claim true opacity readback. If the integrator wires a CLiC LOCK or a parallel sense, that does not change this; real glass feedback would only come from the HC-108 REST API (future, out of scope).

> Verification flag for IMPLEMENT: the official `lutron_caseta` docs enumerate dimmers/switches/shades/fans/sensors/keypad buttons but do **not** explicitly list **CCO / QSE-IO / HWI-CCO-8** output modules. QSX CCO outputs are programmed in the Lutron designer (HWI-CCO-8 / relay outputs support **NO/NC** and **momentary/maintained** per output). They are expected to surface as `switch` entities via LEAP, but this must be **confirmed on the actual QSX system** once a CCO output is programmed (does it appear, and does it appear as a controllable `switch`?). If a maintained CCO does NOT surface as a switch, fallbacks are: a QSX phantom/integration button or a `lutron_caseta` scene/keypad that toggles the CCO. Confirm before LOCKing the contract rows.

## 4. b-panels surface plan (PROPOSED — not LOCKED)

Per glass zone (3–4 total), bound to the Lutron CCO **`switch`** entity for that zone:

| Proposed surface | Bind target | Behavior | Gating |
|---|---|---|---|
| **Clear/Private toggle tile** (per zone) | `switch.glass_<zone>` (the Lutron CCO output) | Toggle ON=Clear / OFF=Private. **Toggle, NOT a slider** (binary glass, no opacity). | **Equipment-gated control** — requires approval; UI confirm recommended |
| Optimistic state indicator (optional) | same `switch` state | Shows assumed Clear/Private from the Lutron CCO commanded state; label as "assumed" (no glass feedback) | Display-only |
| Availability/telemetry (optional) | QSX processor / entity availability | Shows whether the Lutron processor/entity is reachable | Display-only |

- Lead with state/telemetry; the toggle is the equipment-gated control.
- Optional later: an "All Glass Private" tile bound to a CCO wired to the HC-108 **Global Override** (forces all panels private) — strong privacy/scene primitive; equipment-gated.
- No `light` brightness, no `number` tint, no `cover` position — none apply to binary PSCT glass.
- **These rows are PROPOSED.** b-panels (separate thread) binds only after the coordinator LOCKs them, which requires the CCO `switch` entities to actually exist and the gate to confirm them. No b-panels code is written here.

## 5. Concrete remaining asks for the user / integrator (ask once)

1. **Spare CCO outputs:** How many **maintained, dry (potential-free) NO** QSX CCO outputs are available and free for glass use? **Need 1 per zone (3 → 3, 4 → 4),** plus optionally 1 for a global "all private" override.
2. **Which QSX module provides them:** Which processor/output module supplies the CCOs (e.g. **HWI-CCO-8** wired contact-closure output interface, or relay outputs on an **LQSE-4S/LQSE-4T** module)? Need model + how many outputs and their NO/NC + momentary/maintained capability.
3. **Final zone count + rooms:** **3 vs 4** glass zones, and the room name for each (e.g. Master Bath, Office Partition, …) so we can name the CCOs/entities (`switch.glass_<room>`).
4. **Controller-to-zone map:** Which zones are on **WD-02.1.4** (1 panel each) vs on the **HC-108** (which channel #), and are any HC-108 channels ganged (multiple panels = one zone)?
5. **CCO mode confirmation (critical):** Confirm each glass CCO output will be programmed **MAINTAINED (latching), normally-open** — **NOT momentary/pulsed.** CLiC needs a held closed=Clear / open=Private level; a pulse will not hold state.
6. **Wiring sign-off (equipment-gated):** Confirm the integrator will wire each CCO **dry** (no voltage) across the controller's **Dry Contact In/TRIG ↔ Ground**, ground-referenced, within 100 m at ≥18 AWG (CL3/CL3P as required).
7. **Optional override/lock:** Do they want an "all glass private" action wired to the HC-108 **Global Override**, and/or any HC-108 **LOCK** inputs used for hardware privacy lockout? (Both optional, equipment-gated.)
