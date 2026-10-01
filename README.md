<p align="center"><img src="custom_components/difluid/brand/logo.png" alt="DiFluid Technology" width="260"></p>

# DiFluid for Home Assistant

**Development status:** a startup regression is under investigation. The test
instrument showed its logo then a black screen while HA was connecting, and
booted normally after disabling the integration. Keep the HA entry disabled
until controlled hardware validation is complete. The current source adds a
boot delay, retry cooldown, and failure cutoff; these safeguards pass automated
tests but have not yet been accepted on hardware. No GitHub release is published.

Local Bluetooth integration for the **DiFluid R2 PP 0–35 Brix** refractometer.
Switch it on, wait for **Connected**, and press **TEST**. Home Assistant records
the completed measurement without the DiFluid app, an account, or cloud access.

**Domain:** `difluid` · **Home Assistant:** 2026.9 or newer · **Verified firmware:** `V025-dirty`

R2 Extract, R2 PU, R1, and other firmware variants are not claimed as supported.
The PP tested here uses encrypted framing that differs from the published
Extract SDK. [Protocol and compatibility details](docs/protocol.md).

## Installation

1. In HACS, open **Custom repositories**, add `https://github.com/Pyrynot/ha-difluid`,
   and choose **Integration**.
2. Download **DiFluid** and restart Home Assistant.
3. Close the DiFluid app and turn on the instrument near an active Bluetooth
   adapter or ESPHome Bluetooth proxy.
4. Accept the discovered device under **Settings → Devices & services**, or use
   **Add integration → DiFluid**.

The GitHub repository must contain the release before HACS can install it.
For manual installation, copy `custom_components/difluid` into your HA
`config/custom_components/` directory and restart HA.

The integration uses Home Assistant's Bluetooth manager and supports active
ESPHome proxies. The peripheral occupies a connection slot while awake. A
passive advertisement-only receiver cannot receive completed measurements.

## Readings and controls

Entities appear when their fields are received. The integration does not invent
readings for absent fields. The device page includes:

- **Brix**, **sample temperature**, **refractive index** (rounded to five decimal
  places), and **battery** from the latest completed sample.
- **Last measurement** (HA receipt time), **measurement device time**, and a
  **Measurement event** carrying the sample ID and all primary values.
- **Connected**, instrument **status**, last error code, firmware, and the active
  concentration profile's index, name, and unit.
- **Measure** and **Refresh device information** buttons.
- **Synchronize clock** and **Timezone offset** controls, disabled by default;
  enable them in the entity settings if wanted. Timezone is a fixed UTC offset
  in half-hour increments; it does not automatically follow daylight saving.
- Additional reported concentration, optical, timing, exposure, and status
  fields as disabled diagnostic sensors. Their raw protocol names are retained
  where units or physical interpretation have not been established.

Battery is the value in the last completed measurement, not a continuous poll.
The generic app's standalone battery-response schema did not match this PP and
is deliberately not decoded as a percentage or charging status.

Calibration is not exposed: its side effects were not hardware-tested. Profile
coefficient editing, Wi-Fi, firmware updates, and offline history retrieval are
also unverified. Existing protocol definitions from related instruments are not
sufficient evidence of PP support. New verified fields and commands can extend
the entities without replacing the integration's design.

## Recording and automations

Keep the instrument connected before pressing TEST. HA waits at least 20 seconds before connecting after wake-up;
the **Connected** entity confirms the notification subscription is active.
Readings remain available after the instrument sleeps, while controls become
unavailable. No tests or clock changes are initiated automatically.

Each successful sample updates the Measurement event, including repeated tests
with equal numeric values. Start/progress packets, errors, and calibration
records do not overwrite the last successful measurement. Exact record replays
are suppressed using the last 64 sample identities, retained across restarts.
An event timestamp is HA's receipt time; the instrument's clock is preserved
separately. Reconnection is not a promise of retrieving measurements made while
HA was disconnected: a durable device history API has not been verified.

HA Recorder normally records the entities automatically; ensure your custom
Recorder include/exclude rules allow them. These are individual samples, not a
continuous process, so sensors intentionally have no long-term statistics
`state_class`. Retention follows your HA Recorder configuration. The integration
also stores the latest sample locally for restoration, without replaying it as
a new measurement event.

Example automation (replace the entity ID with yours):

```yaml
alias: DiFluid completed measurement
triggers:
  - trigger: state
    entity_id: event.r2_pp_refractometer_measurement
conditions:
  - condition: template
    value_template: >-
      {{ trigger.from_state is not none
         and trigger.from_state.state not in ['unknown', 'unavailable']
         and trigger.to_state.state not in ['unknown', 'unavailable']
         and trigger.from_state.state != trigger.to_state.state }}
actions:
  - action: persistent_notification.create
    data:
      title: DiFluid measurement
      message: >-
        {{ trigger.to_state.attributes.brix | round(1) }} °Bx,
        {{ trigger.to_state.attributes.temperature | round(1) }} °C,
        RI {{ trigger.to_state.attributes.refractive_index }}
```

The condition avoids notifications during HA state restoration. To handle the
first-ever measurement as well, use a trigger/condition suitable for your
installation's startup behavior.

## Troubleshooting

- **Not discovered:** wake the PP, close the vendor app, check active Bluetooth
  coverage and free proxy connection slots. Only names matching `R2 PP *` with
  service `A0FF` are discovered.
- **Logo followed by a black screen:** disable the DiFluid entry, close the app,
  and retry power-on without a Bluetooth connection. This behavior is being
  investigated; do not repeatedly re-enable the integration to retry it.
- **Connection blocked:** automatic attempts stop after three connection failures
  or short-lived connections. Repeated advertisements cannot bypass the
  60-second cooldown. Leave the entry disabled if the instrument is affected;
  reloading is an explicit reset of the attempt limit.
- **Disconnected:** the PP automatically sleeps; this is normal. Leave HA
  running and wake the instrument. No app pairing or account is required.
- **Connected but no result:** wait for a completed successful TEST. An error
  updates status/error code but retains the previous reading. Download
  diagnostics and include the model/firmware when reporting an issue.
- **Equal measurements:** use the Measurement event, whose sample ID distinguishes
  separate tests; do not rely only on a numeric sensor crossing a threshold.
- **Wrong time:** the device timestamp and HA receipt time may differ. Enable
  Synchronize clock and set the device timezone if desired.
- **Using the app temporarily:** disable the integration entry first so both
  clients do not compete for the peripheral, then re-enable it afterward.

Diagnostics omit Bluetooth addresses, serial numbers, raw packets, and sample
values. Debug logging can include transport error details. Unloading disconnects
and cancels listeners; removing the entry deletes its private latest-sample
storage. HA's existing Recorder history follows HA's normal retention policy.

## Development

```sh
uv sync --locked
uv run ruff check custom_components tests tools
uv run ruff format --check custom_components tests tools
uv run mypy custom_components/difluid --follow-imports=silent
uv run pytest -q
```

Tests include sanitized hardware frames, escaping and fragmentation, error and
calibration rejection, BLE response routing/cancellation, config flows, actual
HA entity setup, sample restoration, and replay suppression. No test connects to
hardware. `tools/` contains optional development capture helpers; these are not
used by the integration and should not run alongside HA's connection.

The software is MIT licensed; [brand assets have separate attribution](docs/branding.md).
