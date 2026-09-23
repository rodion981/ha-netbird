<p align="center">
  <img src="custom_components/netbird/brand/icon.png" alt="NetBird" width="180">
</p>

<h1 align="center">NetBird for Home Assistant</h1>
<p align="center">Monitor NetBird Cloud peers and Networks from Home Assistant.</p>

<p align="center">
  <a href="https://github.com/rodion981/ha-netbird/actions/workflows/ci.yml"><img src="https://github.com/rodion981/ha-netbird/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="MIT License"></a>
</p>

[**English**](README.md) | [Українською](README.uk.md)

<p align="center">
  <a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=rodion981&amp;repository=ha-netbird&amp;category=integration"><img src="https://my.home-assistant.io/badges/hacs_repository.svg" alt="Open NetBird in HACS"></a>
</p>

NetBird for Home Assistant is an independently maintained, read-only custom integration for [NetBird Cloud](https://netbird.io/). It shows account and peer status plus current Networks, Resources, and Routers topology from the Management API. A peer marked connected is connected to the Management Service; this does **not** prove end-to-end VPN reachability.

## Project status

Version `0.2.0` adds useful peer diagnostics and current NetBird Networks topology. Install it as a HACS custom repository or manually. The HACS button opens this repository directly; it does not imply listing in the HACS default store.

## Features

- One Cloud account per configuration entry, authenticated by personal access token (PAT).
- One coordinated peer list poll every 60 seconds; new peers appear without a reload.
- Account sensors: peer, network, resource, and router totals.
- Peer states: connection, last seen, IP address, accessible peers, last login, SSH, ephemeral, login expired, and approval required when supplied by the API.
- Optional peer diagnostics disabled by default: IPv6 address, hostname, DNS label, and operating system.
- Current NetBird **Networks**, Resources, and Routers with per-network summaries and resource devices. Deprecated legacy Routes are intentionally excluded.
- Independent topology polling every five minutes with at most six nested requests in flight. A refresh costs `1 + 2N` API requests for `N` networks.
- Redacted aggregate diagnostics and a Repair when stale peer cleanup is blocked.
- English and Ukrainian interface translations.

Only the fixed `https://api.netbird.io` Cloud endpoint is supported. Self-hosted endpoints, legacy Routes, write actions, traffic metrics, and VPN path tests are outside this release.

## Installation

Requires Home Assistant `2026.9.3` or newer and a Cloud PAT able to read the account, peers, Networks, Resources, and Routers. Home Assistant supplies its own Python runtime. Development requires Python `3.14.2` or newer.

### HACS custom repository

Use the HACS button above or:

1. Open **HACS > Custom repositories**.
2. Add `https://github.com/rodion981/ha-netbird` as **Integration**.
3. Open **NetBird** and select **Download**.
4. Restart Home Assistant.
5. Open **Settings > Devices & services > Add integration**, select **NetBird**, and enter your PAT.

The button opens HACS; downloading and setting up the integration remain separate steps. If HACS cannot access the repository, install manually.

### Dashboard example

The [universal NetBird dashboard](examples/netbird-dashboard.yaml) is one native Markdown card. It discovers entities through the integration and stable `netbird_key`, so it does not depend on generated entity IDs or peer names.

1. Create an empty dashboard in Home Assistant.
2. Open its **Raw configuration editor** and paste the example YAML.

The dashboard shows account totals, useful peer details, Networks, and network resources. Missing entities render as `—`; unknown and unavailable remain distinct from `false` and zero. It requires no third-party dashboard card.

### Manual installation and upgrades

Copy `custom_components/netbird` into the Home Assistant configuration directory as `custom_components/netbird`. Restart Home Assistant and add **NetBird** under **Devices & services**. To upgrade manually, back up your configuration, replace that directory with a chosen version, and restart. For HACS upgrades, use the HACS update flow and restart Home Assistant.

## Configuration and PAT rotation

Setup validates the PAT against the Cloud account and peer endpoints. The account ID prevents duplicate entries. A PAT for another account cannot replace the existing entry's token.

Create a replacement PAT for the same account. Open the NetBird entry and choose **Reconfigure**. The new PAT is validated before saving and reloading. Confirm recovery, then revoke the old PAT. HTTP 401 starts Home Assistant reauthentication. HTTP 403 means insufficient permissions; a generic HTTP 404 is not treated as proof that the PAT expired.

## Data updates and availability

The integration polls peers every 60 seconds with one shared coordinator. A separate coordinator polls Networks every 300 seconds. After the network list, Resources and Routers are fetched with a shared concurrency limit of six. A failed nested section affects only that network section; a failed topology refresh does not affect peer states.

Connected routing peers counts only routers linked to a concrete connected peer ID. Group-based routers are excluded because the API does not identify one concrete peer for them, so the value can be zero while group-based routers exist.

Failed refreshes make coordinator entities unavailable rather than showing stale values as current. A peer absent from a successful list becomes unavailable. A missing optional boolean leaves its sensor unavailable rather than showing `off`. A missing or invalid last seen timestamp produces no value. The connected flag does not test VPN routing, DNS, ACLs, or peer-to-peer traffic.

After 10 consecutive **successful** snapshots omit a peer, its integration-owned registry entries are removed. Failed refreshes do not advance the count; a returning peer resets it. The count is held in memory, so reloads or restarts can delay cleanup. Ambiguous device or entity ownership blocks removal and creates a Home Assistant Repair. Recorder history already stored by Home Assistant follows its own retention settings.

## Privacy and troubleshooting

The PAT is stored in the Home Assistant config entry and sent to NetBird Cloud for API reads. Protect backups and never share the PAT. Enabled peer IP, hostname, DNS label, operating system, and resource address entities are visible to Home Assistant Recorder and may appear in history and backups. The integration adds no separate persistent database. Diagnostics contain only versions, refresh status/error classes, and aggregate counts; never tokens, identities, names, addresses, private URLs, or raw responses. Review any diagnostic export before sharing.

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

The integration reads `GET /api/accounts`, `GET /api/peers`, `GET /api/networks`, `GET /api/networks/{id}/resources`, and `GET /api/networks/{id}/routers` at the fixed Cloud endpoint. It never calls deprecated `/api/routes`. Required IDs and topology fields are validated; optional peer fields may be absent or null. Requests have a 10-second timeout. HTTP 429 and server failures wait for a later poll. NetBird [notes that API error handling is still beta](https://docs.netbird.io/api/guides/errors); a generic HTTP 404 is not interpreted as PAT expiry. See the [API reference](https://docs.netbird.io/api). Repository tests use anonymized fixtures and mocked responses; hosted CI verifies that implementation, but no manual live API contract validation of the complete v0.2.0 endpoint set is claimed.

## Development and support

See the [quality checklist and reproducible gate](docs/QUALITY_SCALE.md) and [contribution guide](CONTRIBUTING.md). Runtime tests require Linux or WSL because Home Assistant imports POSIX-only `fcntl`; Windows supports static checks. Report reproducible bugs through [GitHub Issues](https://github.com/rodion981/ha-netbird/issues) without tokens, private URLs, raw responses, or unredacted diagnostics.

The NetBird logomark comes from the [official NetBird press kit](https://netbird.io/press) and remains a NetBird brand asset.
