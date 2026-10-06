<p align="center">
  <img src="custom_components/netbird/brand/icon.png" alt="NetBird" width="180">
</p>

<h1 align="center">NetBird for Home Assistant</h1>
<!-- netbird-doc-contract: {"release":"1.0.2","endpoints":["/api/accounts","/api/peers","/api/networks","/api/networks/{id}/resources","/api/networks/{id}/routers"],"group_router_resolution":"supported","evidence":["mocked-tests","hosted-ci","manual-live"],"distribution":["hacs-custom","manual"],"branding":"included"} -->
<p align="center">Monitor NetBird Cloud or self-hosted peers and Networks from Home Assistant.</p>

<p align="center">
  <a href="https://github.com/rodion981/ha-netbird/actions/workflows/ci.yml"><img src="https://github.com/rodion981/ha-netbird/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="MIT License"></a>
</p>

[**English**](README.md) | [Українською](README.uk.md)

<p align="center">
  <a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=rodion981&amp;repository=ha-netbird&amp;category=integration"><img src="https://my.home-assistant.io/badges/hacs_repository.svg" alt="Open NetBird HA Monitor in HACS"></a>
</p>

NetBird for Home Assistant is an independently maintained, read-only custom integration for [NetBird](https://netbird.io/), using either NetBird Cloud or an explicit self-hosted HTTPS endpoint. It shows account and peer status plus current Networks, Resources, and Routers topology from the Management API. A peer marked connected is connected to the Management Service; this does **not** prove end-to-end VPN reachability.

## Project status

[Version `1.0.2`](https://github.com/rodion981/ha-netbird/releases/tag/v1.0.2) fixes peer cleanup deleting active Network resources, validates self-hosted DNS answers at connection time, and refreshes device names and peer client versions without changing identity. It retains Cloud and self-hosted monitoring, private CA trust, group-aware routing availability, and the responsive English/Ukrainian dashboards. Install it as a HACS custom repository or manually; this does not imply listing in the HACS default store.

## Features

- One Cloud or self-hosted account per configuration entry, authenticated by personal access token (PAT).
- One coordinated peer list poll every 60 seconds; new peers appear without a reload.
- Account sensors: peer, network, resource, and router totals.
- Peer states: connection, last seen, IP address, accessible peers, last login, SSH, ephemeral, login expired, and approval required when supplied by the API.
- Optional peer diagnostics disabled by default: IPv6 address, hostname, DNS label, and operating system.
- Current NetBird **Networks**, Resources, and Routers with per-network summaries and resource devices. Deprecated legacy Routes are intentionally excluded.
- Group-aware Network routing summaries plus a per-resource **Routing available** state that never claims end-to-end reachability.
- Independent topology polling every five minutes with at most six nested requests in flight. A refresh costs `1 + 2N` API requests for `N` networks.
- Redacted aggregate diagnostics and a Repair when stale peer cleanup is blocked.
- English and Ukrainian interface translations.

Cloud uses the fixed `https://api.netbird.io` origin. Self-hosted setup requires an explicit HTTPS API origin, an optional separate HTTPS dashboard origin, and optionally a PEM CA bundle. HTTP, disabled TLS verification, URL path prefixes, redirects, mTLS, discovery, MSP/multi-tenant selection, legacy Routes, write actions, traffic metrics, and VPN path tests are not supported.

## Installation

Requires Home Assistant `2026.9.3` or newer and a PAT able to read the account, peers, Networks, Resources, and Routers. A self-hosted server must expose the same consumed Management API contract over HTTPS. Home Assistant supplies its own Python runtime. Development requires Python `3.14.2` or newer.

### HACS custom repository

Use the HACS button above or:

1. Open **HACS > Custom repositories**.
2. Add `https://github.com/rodion981/ha-netbird` as **Integration**.
3. Open **NetBird HA Monitor** and select **Download**.
4. Restart Home Assistant.
5. Open **Settings > Devices & services > Add integration**, select **NetBird HA Monitor**, choose Cloud or self-hosted, and enter the requested connection data.

The button opens HACS; downloading and setting up the integration remain separate steps. If HACS cannot access the repository, install manually.

### Dashboard example

The [English NetBird dashboard](examples/netbird-dashboard.yaml) and [Ukrainian version](examples/netbird-dashboard.uk.yaml) are responsive native Sections views with separate Overview, Peers, Networks, and Resources cards. They discover entities through the integration and stable `netbird_key`, so they do not depend on generated entity IDs or peer names.

1. Create an empty dashboard in Home Assistant.
2. Open its **Raw configuration editor** and paste the example YAML.

The dashboard demonstrates the main account counts, peer connectivity, IP address, activity timestamps, accessibility, SSH and ephemeral state, network capacity, and resource routing availability. It uses wrapping summaries instead of wide tables and formats timestamps in concise local time. Missing entities render as `—`; unknown and unavailable remain distinct from `false` and zero. It requires no third-party dashboard card.

Home Assistant device pages link to the matching dashboard page only when a dashboard origin is known: `/peers` for the account, `/peer?id=<peer-id>`, `/network?id=<network-id>`, or `/network?id=<network-id>&resource=<resource-id>`. Cloud uses `app.netbird.io`; self-hosted setup uses only the separately entered dashboard origin and never infers it from the API URL. Identifiers are query-encoded independently. These links are best effort because dashboard routes are not a stable NetBird API contract.

### Manual installation and upgrades

Copy `custom_components/netbird` into the Home Assistant configuration directory as `custom_components/netbird`. Restart Home Assistant and add **NetBird HA Monitor** under **Devices & services**. To upgrade manually, back up your configuration, replace that directory with a chosen version, and restart. For HACS upgrades, use the HACS update flow and restart Home Assistant.

## Configuration and PAT rotation

Setup validates the PAT and keeps the account ID as the stable identity. Self-hosted setup additionally validates the complete account, peer, network, resource, and router contract before saving. The account ID prevents duplicate entries across deployment types. A PAT for another account cannot replace the existing entry's token.

Create a replacement PAT for the same account. Reauthentication changes only the PAT. **Reconfigure** rotates a Cloud PAT or atomically replaces the self-hosted API origin, optional dashboard origin, PAT, and CA bundle after full validation. Deployment type cannot be switched in place. Confirm recovery, then revoke the old PAT. HTTP 401 starts Home Assistant reauthentication. HTTP 403 means insufficient permissions; a generic HTTP 404 is not treated as proof that the PAT expired.

## Data updates and availability

The integration polls peers every 60 seconds with one shared coordinator. A separate coordinator polls Networks every 300 seconds. After the network list, Resources and Routers are fetched with a shared concurrency limit of six. A failed nested section affects only that network section; a failed topology refresh does not affect peer states.

Connected routing peers resolves enabled routers addressed to either a concrete peer or a peer group, deduplicates peers selected through multiple paths, and counts their Management Service connection state. Incomplete router, group, peer, or connection data makes the count unavailable instead of silently lowering it.

Routing available is `on` when an enabled resource has at least one resolved connected routing peer. It is `off` when the resource is disabled, no enabled routers exist, or every fully resolved routing peer is explicitly disconnected. Incomplete information is unavailable unless another complete path already proves `on`. This is routing configuration and Management Service evidence, not an ACL, DNS, traffic, or end-to-end VPN test.

Failed refreshes make coordinator entities unavailable rather than showing stale values as current. A peer absent from a successful list becomes unavailable. A missing optional boolean leaves its sensor unavailable rather than showing `off`. A missing or invalid last seen timestamp produces no value. The connected flag does not test VPN routing, DNS, ACLs, or peer-to-peer traffic.

After 10 consecutive **successful** snapshots omit a peer, its integration-owned registry entries are removed. Failed refreshes do not advance the count; a returning peer resets it. The count is held in memory, so reloads or restarts can delay cleanup. Ambiguous device or entity ownership blocks removal and creates a Home Assistant Repair. Recorder history already stored by Home Assistant follows its own retention settings.

## Privacy and troubleshooting

The PAT and any custom CA bundle are stored in the Home Assistant config entry; the PAT is sent only to the configured API origin for read-only requests. Every request verifies HTTPS, has a 10-second timeout, and refuses redirects while authorization is attached. Self-hosted hostnames are revalidated on load, and every DNS answer used for a new connection is checked before opening a socket. Private LAN and IPv6 ULA addresses remain supported. Cloud uses the shared Home Assistant HTTP session; self-hosted sessions own a guarded resolver and close on unload or setup failure. Protect backups and never share the PAT. Enabled peer IP, hostname, DNS label, operating system, and resource address entities are visible to Home Assistant Recorder and may appear in history and backups. The integration adds no separate persistent database. Diagnostics expose only deployment class, whether a custom CA exists, versions, refresh status/error classes, and aggregate counts; never tokens, identities, names, addresses, URLs, certificates, redirect targets, or raw responses. Review any diagnostic export before sharing.

| Symptom | Check |
| --- | --- |
| Authentication failure | Rotate the PAT for the same account through **Reconfigure** or the reauthentication flow. |
| Permission error | Check PAT account access and permissions; HTTP 403 is not automatically treated as expiry. |
| Cannot connect or invalid response | For Cloud, check `https://api.netbird.io` and service status. For self-hosted, check the final HTTPS API origin, DNS, certificate chain, PAT permissions, and required endpoints. Redirects are rejected. |
| Peer unavailable | Check last successful refresh and whether the peer remains in NetBird. Optional fields can make individual sensors unavailable. |
| Stale peer remains | Wait for 10 successful missing-peer snapshots; check **Settings > Repairs**. |
| Connected but traffic fails | Check NetBird clients, routing, DNS, policy, and destination directly. |

To remove the integration, delete its entry in **Settings > Devices & services > NetBird HA Monitor**. Remove the HACS installation or manual `custom_components/netbird` directory afterward and restart. Revoke an unused PAT separately in NetBird. Home Assistant history and backups have separate retention policies.

## API contract and limits

The integration reads `GET /api/accounts`, `GET /api/peers`, `GET /api/networks`, `GET /api/networks/{id}/resources`, and `GET /api/networks/{id}/routers` at either the fixed Cloud origin or a normalized self-hosted HTTPS origin. It never calls deprecated `/api/routes` or adds a groups request. Self-hosted compatibility is capability-based: setup requires all consumed endpoint shapes instead of guessing support from a server version. Required IDs and topology fields are validated; optional peer and group fields may be absent or null. HTTP 429 and server failures wait for a later poll. NetBird [notes that API error handling is still beta](https://docs.netbird.io/api/guides/errors); a generic HTTP 404 is not interpreted as PAT expiry. Repository tests use anonymized fixtures and mocked responses. The protected [Cloud live API contract run](https://github.com/rodion981/ha-netbird/actions/runs/36159603786/job/108170984157) from 25 September 2026 is point-in-time Cloud shape evidence only. Self-hosted release evidence must separately record the tested NetBird version, HTTPS deployment style, setup/reload/poll, reauth, reconfigure, redirect/TLS failure, and private-CA result without retaining private values.

## Development and support

See the [quality checklist and reproducible gate](docs/QUALITY_SCALE.md) and [contribution guide](CONTRIBUTING.md). Runtime tests require Linux or WSL because Home Assistant imports POSIX-only `fcntl`; Windows supports static checks. Report reproducible bugs through [GitHub Issues](https://github.com/rodion981/ha-netbird/issues) without tokens, private URLs, raw responses, or unredacted diagnostics.

The NetBird logomark comes from the [official NetBird press kit](https://netbird.io/press) and remains a NetBird brand asset.
