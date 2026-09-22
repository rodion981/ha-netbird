# Changelog

All notable changes to this project are documented here. The project follows [Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-09-22

### Added

- Useful peer states: IP address, accessible peers, last login, SSH, ephemeral, login expiry, approval status, and optional IPv6/hostname/DNS/OS diagnostics.
- Read-only Networks, Resources, and Routers monitoring with an independent five-minute coordinator, bounded concurrency, and partial-section availability.
- Account and network totals, dynamic resource devices, conservative cleanup, and aggregate-only topology diagnostics.
- Native dynamic Markdown dashboard with no third-party cards or fixed entity IDs.

### Changed

- Existing integration-disabled last-seen and approval entities are enabled during the version-2 migration; user-disabled entities stay disabled.
- Peer and topology entities expose the stable `netbird_key` used by the dashboard.

### Privacy

- Enabled IP, hostname, DNS, operating-system, and resource-address states can be retained by Home Assistant Recorder.
- Diagnostics continue to exclude tokens, identifiers, names, addresses, private URLs, and raw API payloads.

## [0.1.0] - 2026-09-22

### Added

- UI setup and reauthentication for one NetBird Cloud account using a personal access token.
- Read-only, 60-second coordinated polling of the account peer list.
- Account peer counts and per-peer connectivity, login expiry, approval, and last-seen entities.
- Dynamic peer discovery and conservative cleanup after 10 successful missing-peer snapshots.
- Secret-safe diagnostics, translated Repairs, and English and Ukrainian interface text.
- HACS custom-repository metadata, bilingual documentation, and a reproducible quality gate.

### Security and privacy

- Requests use Home Assistant's shared async HTTP session and a 10-second timeout.
- Logs and diagnostics exclude tokens, raw API responses, private addresses, and peer identities.

[0.1.0]: https://github.com/rodion981/ha-netbird/releases/tag/v0.1.0
[0.2.0]: https://github.com/rodion981/ha-netbird/releases/tag/v0.2.0
