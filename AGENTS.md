# DiFluid integration

Domain: `difluid`. Target hardware: R2 PP 0–35; model and firmware support must be verified using real captures. Extract/PU protocol similarity is a hypothesis, not proof.

- Forgejo remote is `origin`; GitHub remote is `github`. Do not push GitHub until implementation and hardware acceptance are complete.
- Expose all verified device capabilities, including results, settings, and controls. Do not freeze an entity list before protocol discovery.
- The primary workflow is a physical TEST followed by automatic HA recording, without the vendor app or cloud.
- Never treat calibration/progress/error packets as completed measurements, or merge identical consecutive tests.
- Keep protocol parsing independent of HA imports. Use HA Bluetooth infrastructure in the integration; standalone proxy utilities are development tools only.
- Never commit credentials, identifying raw captures, or live HA configuration. Sanitize fixtures and record their provenance.
- Discovery may subscribe and read verified fields; it must not initiate tests, calibration, firmware updates, or setting changes automatically.
