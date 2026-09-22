<h1 align="center">NetBird for Home Assistant</h1>
<p align="center">Monitor NetBird Cloud peers from Home Assistant.</p>

<p align="center">
  <a href="README.md"><img src="https://img.shields.io/badge/lang-English-blue" alt="English"></a>
  <a href="README.uk.md"><img src="https://img.shields.io/badge/lang-Українська-yellow" alt="Українська"></a>
  <a href="https://github.com/rodion981/ha-netbird/actions/workflows/ci.yml"><img src="https://github.com/rodion981/ha-netbird/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="MIT License"></a>
</p>
<p align="center">
  <a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=rodion981&amp;repository=ha-netbird&amp;category=integration"><img src="https://my.home-assistant.io/badges/hacs_repository.svg" alt="Open NetBird in HACS"></a>
</p>

NetBird for Home Assistant is an independently maintained, read-only custom integration for [NetBird Cloud](https://netbird.io/). It shows account peer counts and peer status from the Management API. A peer marked connected is connected to the Management Service; this does **not** prove end-to-end VPN reachability.

## Project status

Version `0.1.0` is the first public release. Install it as a HACS custom repository or manually. The HACS button opens this repository directly; it does not imply listing in the HACS default store.

## Features

- One Cloud account per configuration entry, authenticated by personal access token (PAT).
- One coordinated peer list poll every 60 seconds; new peers appear without a reload.
- Account sensors: total peer count and connected peer count.
- Peer binary sensors: connected, login expired, and approval required. Approval required is disabled by default and created only if supplied by the API.
- Peer last seen timestamp, disabled by default. Missing or invalid timestamps have no value.
- Redacted aggregate diagnostics and a Repair when stale peer cleanup is blocked.
- English and Ukrainian interface translations.

Only the fixed `https://api.netbird.io` Cloud endpoint is supported. Self-hosted endpoints and topology entities are post-`0.1.0` work. Legacy Routes, write actions, traffic metrics, and VPN path tests are outside this release.

## Installation

Requires Home Assistant `2026.9.3` or newer and a Cloud PAT able to read the account and peers. Home Assistant supplies its own Python runtime. Development requires Python `3.14.2` or newer.

### HACS custom repository

Use the HACS button above or:

1. Open **HACS > Custom repositories**.
2. Add `https://github.com/rodion981/ha-netbird` as **Integration**.
3. Open **NetBird** and select **Download**.
4. Restart Home Assistant.
5. Open **Settings > Devices & services > Add integration**, select **NetBird**, and enter your PAT.

The button opens HACS; downloading and setting up the integration remain separate steps. If HACS cannot access the repository, install manually.

### Manual installation and upgrades

Copy `custom_components/netbird` into the Home Assistant configuration directory as `custom_components/netbird`. Restart Home Assistant and add **NetBird** under **Devices & services**. To upgrade manually, back up your configuration, replace that directory with a chosen version, and restart. For HACS upgrades, use the HACS update flow and restart Home Assistant.

## Configuration and PAT rotation

Setup validates the PAT against the Cloud account and peer endpoints. The account ID prevents duplicate entries. A PAT for another account cannot replace the existing entry's token.

Create a replacement PAT for the same account. Open the NetBird entry and choose **Reconfigure**. The new PAT is validated before saving and reloading. Confirm recovery, then revoke the old PAT. HTTP 401 starts Home Assistant reauthentication. HTTP 403 means insufficient permissions; a generic HTTP 404 is not treated as proof that the PAT expired.

## Data updates and availability

The integration polls peers every 60 seconds with one shared coordinator. Account sensors count the latest successful peer list; connected count includes only explicit `connected: true`. No traffic probe or push update is used.

Failed refreshes make coordinator entities unavailable rather than showing stale values as current. A peer absent from a successful list becomes unavailable. A missing optional boolean leaves its sensor unavailable rather than showing `off`. A missing or invalid last seen timestamp produces no value. The connected flag does not test VPN routing, DNS, ACLs, or peer-to-peer traffic.

After 10 consecutive **successful** snapshots omit a peer, its integration-owned registry entries are removed. Failed refreshes do not advance the count; a returning peer resets it. The count is held in memory, so reloads or restarts can delay cleanup. Ambiguous device or entity ownership blocks removal and creates a Home Assistant Repair. Recorder history already stored by Home Assistant follows its own retention settings.

## Privacy and troubleshooting

The PAT is stored in the Home Assistant config entry and sent to NetBird Cloud for API reads. Protect backups and never share the PAT. Peer names, addresses, and status may appear in Home Assistant entities, history, and backups. The integration adds no separate persistent peer database. Diagnostics include only version, Cloud deployment class, refresh success/time/error class, and aggregate peer counts; no token, peer identity, address, or raw response. Review any diagnostic export before sharing.

| Symptom | Check |
| --- | --- |
| Authentication failure | Rotate the PAT for the same account through **Reconfigure** or the reauthentication flow. |
| Permission error | Check PAT account access and permissions; HTTP 403 is not automatically treated as expiry. |
| Cannot connect or invalid response | Check access to `https://api.netbird.io` and Cloud service status. |
| Peer unavailable | Check last successful refresh and whether the peer remains in NetBird Cloud. Optional fields can make individual sensors unavailable. |
| Stale peer remains | Wait for 10 successful missing-peer snapshots; check **Settings > Repairs**. |
| Connected but traffic fails | Check NetBird clients, routing, DNS, policy, and destination directly. |

To remove the integration, delete its entry in **Settings > Devices & services > NetBird**. Remove the HACS installation or manual `custom_components/netbird` directory afterward and restart. Revoke an unused PAT separately in NetBird. Home Assistant history and backups have separate retention policies.

## API contract and limits

The integration reads `GET /api/accounts` and `GET /api/peers` at the fixed Cloud endpoint. It expects exactly one account and a peer list with unique, nonempty IDs. Optional peer fields may be absent or null. Malformed required structure rejects a snapshot; invalid optional timestamps become unknown. Requests have a 10-second total timeout. HTTP 429 and server failures wait for a later coordinator poll. The integration implements no pagination and assumes no undocumented fields. NetBird [notes that API error handling is still beta](https://docs.netbird.io/api/guides/errors); status codes can be ambiguous, so a generic HTTP 404 is not interpreted as PAT expiry. See the [API reference](https://docs.netbird.io/api). Repository tests use anonymized data; this README claims no production live validation.

## Development and support

See the [quality checklist and reproducible gate](docs/QUALITY_SCALE.md) and [contribution guide](CONTRIBUTING.md). Runtime tests require Linux or WSL because Home Assistant imports POSIX-only `fcntl`; Windows supports static checks. Report reproducible bugs through [GitHub Issues](https://github.com/rodion981/ha-netbird/issues) without tokens, private URLs, raw responses, or unredacted diagnostics.
