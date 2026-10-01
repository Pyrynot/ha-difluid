# R2 PP protocol and evidence

## Compatibility boundary

Verified on an R2 PP 0–35 instrument reporting firmware **V025-dirty**, on
2026-10-01. The manufacturer-hosted [DiFluid Tech Android app](https://difluidtech.com/pages/app-download)
provided protocol definitions; actual BLE replies and screen readings establish
which of them apply to this PP. No vendor application source is included here.

App package SHA-256: `ab0ccfb23dacc50c36a6c8ae69ff09d8bc84e6583882754df38a59b650e0ce28`.

Claims in [third-party Extract/PP discussion](https://github.com/Kulitorum/Decenza/pull/1386)
are leads only. The device observed here uses **DADA encrypted frames**, not the
Extract SDK's DFDF frames. Generic PU tail fields and battery layout also differ
from the PP's observed messages; unsupported interpretations are not exposed.

## Startup compatibility remains unverified

The physical TEST-to-Recorder path passed on V025-dirty, but cold-start behavior
subsequently failed: the user saw the boot logo followed by a black screen while
HA attempted connections. After the entry was disabled, the instrument booted
normally. This implicates the connection path but does not isolate whether
connection establishment, notification setup, or metadata queries trigger it.

The integration stays disabled during investigation. The proposed mitigation
waits 20 seconds after discovery, requires a fresh advertisement, enforces a
60-second reconnect cooldown, and stops after three failures/short connections.
Connection setup is bounded to 30 seconds and partial clients are cleaned up.
These changes need controlled hardware testing before any release.

## Transport and framing

- Advertised service: `0000a0ff-0000-1000-8000-00805f9b34fb`.
- Write/notify characteristic: `0000ff01-0000-1000-8000-00805f9b34fb`.
- AA01 is present but not needed for the verified workflow.
- Notifications require enabling the CCCD. HA's Bleak backend handles this for
  local adapters and ESPHome remote-caching connections.
- Frames start `DA DA`, end `0A 0A`. Reserved `DA`, `0A`, and `FA` bytes inside
  the frame are escaped by prefixing `FA`.
- Unescaped body: AES ciphertext, one flags byte, one additive checksum.
  The checksum is the sum of ciphertext and flags modulo 256.
- Flags' low two bits select encryption level 1; upper bits vary.
- AES-128-CBC uses public protocol constants: key
  `00102030405060708090a0b0c0d0e0f0`, IV `000102030405060708090a0b0c0d0e0f`.
  These are not credentials, and no cloud key exchange is involved.
- Decrypted header: `<BBHH` (address, function, register, payload length).
  Payload is followed by little-endian CRC-16/MODBUS of header + payload.
  Device measurement frames can end at a block boundary without PKCS7 padding.
- Outbound commands zero-pad to an 8-byte boundary and then add AES PKCS7
  padding. This matches the manufacturer client and works on the tested PP.
- Address **0** occurs in measurement/clock replies; **1** occurs in firmware,
  profile, identity, and command acknowledgements. Both are valid.

The bounded incremental decoder accepts fragmented and concatenated frames.
It validates escaping, checksums, declared lengths, and CRC before exposing data.
An escaped `0A` immediately before the terminator must not be mistaken for the
start of that terminator.

## Verified messages

| Function/register | Purpose | Observed response |
|---|---|---|
| 3/6 | Unsolicited status/result | 120 bytes |
| 3/0 | Request one measurement | 3/9 acknowledgement, then 3/6 records |
| 3/9 | Command accepted | `0000000001000000` for Measure |
| 3/14 | Read concentration profile | 53 bytes: index, name, unit, coefficients |
| 5/11 | Firmware | 32-byte NUL-padded string |
| 4/1 | Device clock | 8-byte little-endian Unix seconds |
| 4/2 | Timezone | Signed byte, units of 30 minutes |
| 5/2 | Identity | 212 bytes; not needed or persisted |
| 5/28 → 5/6 | Standalone battery query | 8 bytes; semantics unverified |

Clock and timezone writes use the same register and payload format as reads.
All writes are explicit user actions. Measurement writes are never retried
implicitly, since a timeout does not prove the command was not executed.

## Measurement layout

`protocol/measurement.py` defines the verified 89-byte prefix. A 120-byte record
is required; the remaining 31 bytes contribute to the replay fingerprint but
are not assigned generic PU field names. Main fields:

| Offset | Type | Meaning |
|---|---|---|
| 0 | uint64 LE | Device Unix timestamp |
| 12 | float32 LE | Prism/sample temperature, °C |
| 20, 24 | float32 LE | Reported display and real-liquid concentrations |
| 28 | float32 LE | Profile concentration used for PP Brix |
| 36 | float32 LE | Reported display refractive index |
| 40 | float32 LE | Real-liquid refractive index used by the app |
| 46 | uint8 | Reported battery percentage |
| 71 | uint8 | Result/status |
| 72 | uint8 | Error code |
| 73 | uint8 | Model type |

Screen-confirmed examples: 7.5% / 23.7°C / 1.3440 and 8.0% / 24.1°C /
1.3447. The latter raw real-liquid index is approximately 1.344721, so the HA
sensor reports **1.34472** at the requested five-decimal precision. This exposes
reported resolution; it does not assert additional instrument accuracy.

Status 0 with error 0, a nonzero timestamp, and a measurement register is a
completed reading. Status 11 is test start; 12 calibration start; 1 calibration
completion; 2 measurement error; 3 hardware error. Calibration register 3 is
excluded even if its status happens to be 0. Non-finite values and unsupported
record lengths are rejected. Optical/internal field names come from the app's
prefix map and remain opt-in diagnostics without guessed units.

A sample ID combines device timestamp and SHA-256 of the full payload (truncated
to 16 hexadecimal digits). The last 64 IDs are retained. This suppresses exact
replays across reconnect/restart while preserving equal readings from separate
tests. It cannot recover device history or distinguish hypothetical byte-for-byte
identical records; the PP's hardware sequence-field location remains unverified.

## Home Assistant design references

- [Bluetooth best practices](https://developers.home-assistant.io/docs/bluetooth/)
  and [Bluetooth APIs](https://developers.home-assistant.io/docs/core/bluetooth/api/).
- [Config flows](https://developers.home-assistant.io/docs/config_entries_config_flow_handler/)
  and [manifest requirements](https://developers.home-assistant.io/docs/creating_integration_manifest/).
- [Event entities](https://developers.home-assistant.io/docs/core/entity/event/)
  and [sensor entities](https://developers.home-assistant.io/docs/core/entity/sensor/).
- [Local brand images](https://developers.home-assistant.io/docs/core/integration/brand_images/).
- [HACS integration requirements](https://www.hacs.xyz/docs/publish/integration/).
