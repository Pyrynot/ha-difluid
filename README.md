<p align="center">
  <img src="custom_components/difluid/brand/logo.png" alt="DiFluid" width="260">
</p>

# DiFluid for Home Assistant

Record refractometer measurements in Home Assistant over local Bluetooth.
Turn on your **DiFluid R2 PP**, wait for it to connect, and press **TEST** on the
instrument. Your completed measurement appears in Home Assistant automatically,
without the DiFluid app or a cloud account.

[![Validate](https://github.com/Pyrynot/ha-difluid/actions/workflows/validate.yml/badge.svg)](https://github.com/Pyrynot/ha-difluid/actions/workflows/validate.yml)
[![Release](https://img.shields.io/github/v/release/Pyrynot/ha-difluid)](https://github.com/Pyrynot/ha-difluid/releases)

- Brix, sample temperature, refractive index, and battery readings.
- A measurement event for automations, including consecutive tests with equal values.
- Last successful readings retained when the instrument sleeps or HA restarts.
- On-demand measurement and device-information controls.
- Local Bluetooth adapters and active ESPHome Bluetooth proxies.
- DiFluid logo and icon included for the Home Assistant device page.

This is an independent community integration, not an official DiFluid product.

## Compatibility

| Requirement | Supported configuration |
| --- | --- |
| Instrument | **DiFluid R2 PP, 0–35 Brix** |
| Verified instrument firmware | `V025-dirty` |
| Home Assistant | **2026.9.0 or newer** |
| Bluetooth | HA Bluetooth integration with a connectable adapter or active ESPHome proxy |
| Installation | HACS custom repository or manual installation |
| Integration domain | `difluid` |

Other firmware versions have not been verified. **R2 Extract, R2 PU, R1, and
other DiFluid models are not currently supported.** Similar product names or
third-party compatibility reports do not establish protocol compatibility.
See [protocol and hardware validation](docs/protocol.md) for the evidence behind
the supported features.

## Install through HACS

Install [HACS](https://www.hacs.xyz/docs/use/) first if it is not already available.
This integration is installed as a **custom repository**; it is not listed in the
default HACS catalog.

1. Open **HACS → ⋮ → Custom repositories**.
2. Add `https://github.com/Pyrynot/ha-difluid` and select **Integration** as the type.
3. Find **DiFluid** in HACS and download the latest release.
4. Restart Home Assistant.
5. Close the DiFluid app and turn on the R2 PP within Bluetooth range.
6. Open **Settings → Devices & services** and configure the discovered DiFluid
   device. Alternatively, choose **Add integration → DiFluid**.

No YAML configuration, account, or app pairing is required. Future releases can
be installed through HACS; restart Home Assistant after an update.

### Manual installation

Download a [release](https://github.com/Pyrynot/ha-difluid/releases) and copy its
`custom_components/difluid` directory into your Home Assistant configuration
directory at `config/custom_components/difluid`. Restart HA, then follow steps
5–6 above.

## Take a measurement

1. Keep the DiFluid app closed so Home Assistant can connect to the instrument.
2. Turn on the R2 PP and wait until its **Connected** entity is on. The integration
   deliberately waits at least **20 seconds** before connecting after discovery.
3. Prepare your sample and press **TEST** on the instrument.
4. When the test finishes successfully, Home Assistant updates the readings and
   the **Measurement** event.

The instrument can sleep normally afterward. The last successful readings remain
available, while device controls become unavailable until it reconnects. Home
Assistant never starts a measurement or changes the device clock automatically.

Keep HA connected while testing: retrieval of measurements taken while
disconnected is not supported. A passive Bluetooth receiver cannot receive
measurement notifications; an ESPHome proxy needs active connections enabled
and a free connection slot.

## Entities and controls

Entities are added as the instrument reports the corresponding fields. Optional
diagnostics and settings are disabled by default and can be enabled from their
entity settings.

| Feature | What it provides |
| --- | --- |
| Brix | Concentration from the PP's reported Brix profile |
| Sample temperature | Reported prism/sample temperature in °C |
| Refractive index | Reported value rounded to **five decimal places** |
| Battery | Percentage reported with the last completed measurement |
| Last measurement | Time Home Assistant received the sample |
| Measurement device time | Timestamp reported by the instrument |
| Measurement event | A distinct completed sample, its ID, timestamps, and primary readings |
| Connected and Status | Bluetooth subscription and instrument/connection state |
| Device information | Firmware, profile index/name/unit, and last error code |
| Measure | Request a single measurement from Home Assistant |
| Refresh device information | Read firmware, profile, clock, and timezone |
| Synchronize clock | Optional control to set the instrument clock |
| Timezone offset | Optional fixed UTC offset in half-hour increments |
| Additional diagnostics | Reported concentration, optical, timing, exposure, and status fields |

Battery is not continuously polled. Five-decimal refractive-index reporting does
not imply greater instrument accuracy. Diagnostic fields retain protocol names
where their units or physical meaning are not established.

Clock and timezone reads have been verified on hardware; their optional setting
controls have automated tests but have not been hardware-tested. The timezone
is a fixed offset and does not automatically follow daylight saving time.

Calibration, profile editing, Wi-Fi setup, firmware updates, and offline history
retrieval are not exposed because they have not been verified on the R2 PP.

## History and automations

Home Assistant's Recorder normally saves the sensor states and measurement
events. If you use Recorder include/exclude rules, allow the DiFluid entities.
History retention follows your Recorder settings. These are individual samples,
so the sensors do not generate long-term statistics.

Use the **Measurement event** for automations that must distinguish separate
tests with equal Brix values. Start/progress, failed tests, and calibration
records do not replace a successful reading. Exact record replays are suppressed
across reconnects and restarts.

Example notification automation — replace the entity ID with the one on your
DiFluid device page:

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

This conservative example skips transitions from unknown/unavailable states,
including the first-ever event, to avoid a notification on state restoration.
Adapt that condition if your automation also needs to handle the first event.
Event attributes include `measurement_id`, `device_time`, `received_at`, `brix`,
`temperature`, `refractive_index`, and `battery`.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Device not discovered | Wake the PP, close the app, and check Bluetooth coverage and free active proxy slots. Discovery matches `R2 PP *` devices advertising service `A0FF`. |
| Disconnected | The instrument may have gone to sleep. Wake it and wait for **Connected** before testing. |
| Connected but no new reading | Only a completed successful TEST updates the sample. Check Status and Last error code. |
| Connection blocked | Automatic attempts stop after three failures or short connections. Check coverage and device behavior before reloading the integration to reset the limit. |
| Unexpected timestamp | Compare HA receipt time with Measurement device time. The instrument clock and timezone are separate from HA's. |
| Need to use the DiFluid app | Disable the integration entry while using the app, then re-enable it afterward. |

**Boot logo followed by a black screen:** this was observed on the tested PP
with early versions that connected immediately during startup. The current
build waits before connecting, enforces retry limits, and passed a monitored
startup check. The exact firmware trigger remains unproven. If it occurs,
disable the integration, close the app, and retry power-on without a Bluetooth
connection before making further connection attempts.

Physical TEST recording and Recorder persistence were verified on hardware.
After the startup safeguards were added, connection and metadata reads were
verified again; a fresh-sample measurement was not repeated. See the
[validation details](docs/protocol.md#startup-safeguards-and-validation).

## Report an issue or contribute

[Open an issue](https://github.com/Pyrynot/ha-difluid/issues) with your exact model,
firmware, HA version, integration version, Bluetooth adapter/proxy type, and steps
to reproduce the problem. Attach the integration diagnostics from the device
page when useful. Diagnostics omit Bluetooth addresses, serial numbers, raw
packets, and sample values; review any additional debug logs before sharing them.

Contributions for other models are welcome, but support needs device-specific
captures and validation. The [protocol documentation](docs/protocol.md) separates
verified behavior from unconfirmed fields and commands.

Development requires Python 3.14.2 or newer and [uv](https://docs.astral.sh/uv/):

```sh
uv sync --locked
uv run ruff check custom_components tests tools
uv run ruff format --check custom_components tests tools
uv run mypy custom_components/difluid --follow-imports=silent
uv run pytest -q
```

Tests use sanitized fixtures and do not connect to hardware. The optional capture
utilities in `tools/` are for development and must not run alongside HA's device
connection.

## License

Integration code is available under the [MIT license](LICENSE). DiFluid logos and
trademarks belong to their respective owners and are excluded from that license;
see [brand attribution](docs/branding.md).
