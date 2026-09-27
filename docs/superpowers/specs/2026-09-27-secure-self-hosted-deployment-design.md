# Secure self-hosted NetBird deployment design

**Issue:** ROD-36  
**Status:** Design complete, ready for approval  
**Implementation issue:** ROD-48  
**Date:** 2026-09-27

## Decision summary

The integration will support two explicit deployment types: the existing
NetBird Cloud service and a user-managed NetBird server. Self-hosted support is
not a generic `CONF_URL` switch. It adds a deployment boundary that owns URL
normalization, TLS trust, redirect policy, dashboard links, config-entry
migration, validation, and diagnostics.

The first self-hosted implementation will:

- require HTTPS for every authenticated API request;
- keep the Management API origin and dashboard origin separate;
- never infer a dashboard URL from the API URL;
- never follow an HTTP redirect while a PAT is attached;
- support a private CA only through an explicitly supplied CA certificate;
- keep the existing account ID as the config-entry, device, and entity identity;
- migrate existing entries to an explicit Cloud deployment without changing
  unique IDs;
- validate compatibility by exercising the read-only API contract rather than
  relying on an undocumented minimum NetBird version;
- change the manifest IoT class from `cloud_polling` to `local_polling`, because
  the integration will offer direct polling of a user-managed server;
- retain the current GET-only behavior, request timeouts, coordinator split,
  data schemas, and conservative availability semantics.

ROD-48 stops when this profile works and is proved. It must not add MSP tenant
selection, OAuth, write operations, endpoint discovery, HTTP fallback, or
client-certificate authentication.

## Evidence used

- NetBird documents PAT authentication with `Authorization: Token` for both its
  public API and self-hosted automation:
  [API authentication](https://docs.netbird.io/api/guides/authentication) and
  [automated self-hosted setup](https://docs.netbird.io/selfhosted/automated-setup).
- Current self-hosted deployments expose REST under `/api` and commonly serve
  the dashboard and API from one public origin, but the dashboard is configured
  with its own Management API endpoint:
  [configuration files](https://docs.netbird.io/selfhosted/maintenance/configuration-files)
  and [external reverse proxy](https://docs.netbird.io/selfhosted/external-reverse-proxy).
- NetBird exposes `/api/instance/version`, but the public documentation does not
  establish a minimum version for every endpoint consumed by this integration:
  [instance API](https://docs.netbird.io/api/resources/instance).
- Home Assistant requires stable unique IDs and treats a URL as an unacceptable
  unique ID. It also distinguishes credential replacement (`reauth`) from
  connection-setting changes (`reconfigure`):
  [config flow](https://developers.home-assistant.io/docs/core/integration/config_flow/).
- Home Assistant defines `local_polling` for direct polling and `cloud_polling`
  for integrations that require an Internet cloud service:
  [integration manifest](https://developers.home-assistant.io/docs/creating_integration_manifest/).

These sources define the current design evidence. They do not replace runtime
validation against a real self-hosted instance.

## Goals

1. Let a Home Assistant administrator add one self-hosted NetBird account with
   a PAT and receive the same peer and topology entities as Cloud.
2. Preserve the existing Cloud experience and all entity/device identities.
3. Prevent PAT disclosure through plaintext transport, redirects, logs,
   diagnostics, dashboard links, or validation errors.
4. Support public CA certificates and an explicit private CA bundle without a
   `verify_ssl: false` escape hatch.
5. Allow a self-hosted server or dashboard address to change through
   reconfiguration when the authenticated account identity stays the same.
6. Make unsupported API capability explicit during setup instead of claiming
   compatibility from a version string alone.

## Non-goals

- MSP or multi-tenant account selection.
- OAuth2, embedded IdP login, username/password login, or token creation.
- HTTP API access, opportunistic TLS, or disabled certificate verification.
- Mutual TLS, client certificates, or private keys.
- Automatic discovery of NetBird, its API origin, or its dashboard origin.
- API deployments below a URL path prefix such as `/netbird/api`.
- Redirect following, even when the redirect appears to stay on the same host.
- Legacy Routes, write actions, traffic telemetry, or reachability probes.
- Supporting two config entries with the same NetBird account ID.
- Copying implementation or documentation from another Home Assistant project.

## Configuration model

### Stored entry data

All entries store:

- `deployment_type`: `cloud` or `self_hosted`;
- `account_id`: the account ID returned by the authenticated API;
- `api_token`: the PAT.

Cloud entries store no user-editable URL. They always use the compiled Cloud
origins:

- API: `https://api.netbird.io`;
- dashboard: `https://app.netbird.io`.

Self-hosted entries additionally store:

- `api_url`: a normalized HTTPS origin;
- `dashboard_url`: a normalized HTTPS origin or no value;
- `ca_certificate`: an optional PEM CA bundle or no value.

The API URL, dashboard URL, PAT, and CA bundle belong in config-entry `data`,
not options. They are required connection inputs and must be changed atomically
through reconfigure or reauth.

### Runtime deployment object

ROD-48 should introduce one immutable runtime/configuration object that resolves
the stored deployment type into:

- API origin;
- optional dashboard origin;
- TLS context policy;
- diagnostic deployment class.

`NetBirdApiClient` receives this resolved API origin and optional SSL context.
It must no longer concatenate request paths with the global Cloud constant.
The request paths and response parsers stay shared between Cloud and
self-hosted deployments.

## URL contract

### API origin

The self-hosted API URL must be an absolute HTTPS origin:

- scheme exactly `https` after normalization;
- non-empty hostname and optional port from 1 through 65535;
- no username or password;
- no path except empty or `/`;
- no query or fragment;
- no control characters;
- stored without a trailing slash and with a normalized lowercase/IDNA host;
- default port `443` omitted from the stored form.

The client appends only its fixed `/api/...` paths. It never accepts an
endpoint path from user input.

Private RFC1918 and IPv6 ULA destinations are intentionally allowed because
local NetBird is the feature. Explicit loopback, unspecified, link-local, and
multicast destinations are rejected. Initial setup and endpoint reconfiguration
must resolve the hostname and reject it when any returned address is in one of
those blocked classes. This check reduces accidental SSRF exposure but does not
turn the integration into a general URL fetcher: only an administrator can set
the origin and only fixed GET paths are requested.

### Dashboard origin

The dashboard URL is optional and independently entered. It uses the same
HTTPS-origin syntax rules. It may use a different host or port from the API.
It is never requested by Home Assistant and never receives the PAT.

When absent, every `DeviceInfo.configuration_url` for that entry is `None`.
When present, the integration builds the existing escaped peer, network, and
resource links relative to that origin. Those deep links remain best effort
because dashboard routes are not a stable API contract.

The integration never derives the dashboard URL from the API URL.

## Transport and redirect policy

All API calls continue to use Home Assistant's injected aiohttp session and a
10-second total timeout. Each call sets:

- `Authorization: Token <PAT>`;
- `Accept: application/json`;
- `allow_redirects=False`;
- the entry-specific SSL context when a private CA is configured.

Every 3xx response is a safe configuration/transport error. The client does
not inspect or log `Location` and never retries the request at another origin.
This is stricter than relying on library behavior to strip authorization during
a cross-origin redirect.

Existing mappings remain unchanged: 401 triggers reauthentication, 403 means
insufficient permission, 429 waits for a later poll, 5xx is retryable, and
response bodies are never included in errors or logs.

## TLS and private CA handling

Certificate verification is always enabled. There is no boolean to disable it.

With no custom CA, the integration uses Home Assistant's normal trust store.
For a private CA, the user supplies a PEM certificate bundle in the
self-hosted form. The implementation must:

1. reject empty, malformed, oversized (more than 64 KiB), or private-key PEM;
2. build a default client SSL context and add the supplied CA certificates;
3. build the context once per validation/runtime setup outside the event loop;
4. preserve hostname and certificate-expiry verification;
5. pass the context per request while still using Home Assistant's shared
   session;
6. store the PEM only in config-entry data and never expose it in diagnostics,
   logs, titles, issues, or Repairs.

Reconfigure can add, rotate, or remove the CA bundle. New connection data is
saved only after the new TLS configuration and PAT validate successfully.

Client certificates and certificate pinning are separate future designs.

## Config-flow behavior

### New setup

The user first chooses `NetBird Cloud` or `Self-hosted NetBird`.

Cloud setup asks only for the PAT and retains the current fixed origins.

Self-hosted setup asks for:

- Management API URL;
- optional dashboard URL;
- PAT;
- optional CA certificate bundle.

Before creating an entry, setup validates URL and CA syntax, builds the client,
and performs the complete existing read-only contract: account, peers,
networks, and the resource/router sections returned for those networks. The
probe uses the existing bounded topology concurrency and retains the current
request budget of `1 + 2N` topology requests for `N` networks.

The form returns separate translated errors for invalid URL, blocked address,
invalid CA, TLS failure, redirect, authentication, permission, unsupported API
shape, timeout, and other connection failure. Error messages never contain the
URL, certificate, PAT, response body, or identifiers.

### Reauthentication

Reauth changes only the PAT. It reconstructs the client from the entry's stored
deployment, API origin, and CA bundle, then requires the same account ID before
an atomic update/reload. Endpoint and CA fields are not accepted in reauth.

### Reconfiguration

For Cloud, reconfigure continues to rotate the PAT only.

For self-hosted, reconfigure can change API URL, dashboard URL, PAT, and CA
bundle together. Suggested non-secret values may be shown. The PAT field stays
masked. The update succeeds only when the new connection returns the existing
account ID and passes the same compatibility validation as initial setup.

Deployment type cannot be changed by reconfigure. Moving between Cloud and
self-hosted is a new entry because it changes the trust boundary. Duplicate
account protection still applies.

## Identity and migration

The NetBird account ID remains `ConfigEntry.unique_id`. A URL is mutable access
data and must not become identity. Account, peer, network, resource, and entity
unique IDs remain unchanged.

Consequences:

- changing a self-hosted origin for the same account preserves history and
  registry ownership;
- existing Cloud entity IDs do not churn;
- a cloned NetBird database with the same account ID is treated as the same
  logical deployment and cannot be configured twice;
- an attempted reauth or reconfigure to a different account aborts without
  changing the entry.

ROD-48 bumps the config-flow version from 2 to 3. Migration adds
`deployment_type=cloud` to every version-2 entry and changes nothing else. It
does not store Cloud URLs, alter the entry unique ID/title, touch entity/device
registries, or reload secrets. Migration is deterministic and can be rolled
back by restoring the pre-migration Home Assistant backup.

## Compatibility and capability detection

No hard minimum NetBird version is claimed in ROD-48. The official version
endpoint exists, but current documentation does not define which version first
provides the exact complete endpoint shapes used here. Rejecting or accepting a
server from a guessed version would be weaker than exercising the contract.

Compatibility therefore means:

- PAT authentication works with `Authorization: Token`;
- `/api/accounts` returns exactly one usable account;
- `/api/peers` matches the existing required/optional schema;
- `/api/networks` and every returned network's `/resources` and `/routers`
  sections match the existing topology schema.

Initial setup and endpoint reconfigure run that capability probe. Ordinary
refreshes retain partial-section isolation so a later transient nested failure
does not erase unrelated current data.

The optional `/api/instance/version` endpoint is not called, persisted, or used
as a gate in ROD-48. A future compatibility policy may add it after evidence
establishes meaningful supported ranges.

Release evidence must record the exact self-hosted NetBird version and
deployment style used for the live test. It must not claim all older or future
versions from one successful run.

## IoT class

The manifest changes to `local_polling`. Home Assistant exposes one IoT class
per integration, not per config entry. Once a user-managed direct endpoint is
supported, the integration no longer inherently requires the NetBird Cloud or
an active Internet connection. Cloud entries remain supported by the same
integration and polling coordinators.

The integration name remains `NetBird`, not `NetBird Local` or `NetBird Cloud`.

## Dashboard and entity behavior

No entity semantics change. Both deployment types use the same two
coordinators, entity descriptions, group-router resolution, routing availability
rules, lifecycle cleanup, and stable `netbird_key` attributes.

The only dashboard-related change is that configuration URLs become
entry-specific and optional. The example Home Assistant dashboard remains
deployment-neutral because it discovers entities, not NetBird web URLs.

## Diagnostics, logging, and privacy

Diagnostics may expose only:

- `deployment_class`: `cloud` or `self_hosted`;
- `custom_ca`: boolean;
- the existing integration version, error classes, timestamps, and aggregate
  counts.

Diagnostics and logs must never expose:

- PAT or authorization header;
- API or dashboard URL, hostname, port, or resolved address;
- CA certificate content or fingerprint;
- redirect target;
- response body;
- account, peer, network, router, group, or resource identifiers.

Connection exceptions are mapped to fixed integration-safe classes before they
reach coordinators or config-flow errors.

## ROD-48 implementation boundary

Expected responsibility changes:

- `const.py`: deployment/config keys and fixed Cloud defaults;
- a small deployment/URL/TLS helper: normalization and SSL-context creation;
- `api.py`: entry-specific origin, SSL context, and redirect refusal;
- `config_flow.py`: deployment selection, self-hosted setup, safe reauth and
  reconfigure;
- `__init__.py`: version-3 migration and runtime client construction;
- `dashboard_urls.py` plus entity constructors: optional entry-specific
  dashboard origin;
- `diagnostics.py`: allowlisted deployment class and custom-CA boolean;
- manifest, strings/translations, README, QUALITY_SCALE, and focused tests.

ROD-48 must reuse the existing parsers, request paths, coordinators, and entity
models. It must not introduce a second self-hosted API client or duplicate
platform logic.

## Required automated tests

### URL and transport

- normalize host case, IDNA, trailing slash, IPv4/IPv6, and default port;
- reject HTTP, credentials, path prefixes, queries, fragments, invalid ports,
  control characters, and missing hosts;
- allow RFC1918/ULA targets;
- reject loopback, unspecified, link-local, multicast, and hostnames resolving
  to those classes;
- append fixed API paths exactly once;
- refuse relative and absolute redirects without issuing a second request;
- preserve the 10-second timeout and existing status/error mapping.

### TLS

- default trust-store path;
- valid private CA bundle;
- malformed/oversized PEM and PEM containing a private key;
- hostname mismatch, expired/untrusted certificate, and successful CA rotation;
- no code path or schema for disabled verification.

### Config flow and migration

- Cloud setup remains PAT-only after deployment selection;
- self-hosted setup stores normalized values only after a successful full probe;
- duplicate account rejection across deployment types;
- same-account reauth changes only PAT;
- different-account reauth/reconfigure preserves the old entry;
- self-hosted reconfigure changes connection inputs atomically and reloads once;
- deployment-type switching is rejected;
- version-2 Cloud migration adds only the deployment type;
- account/device/entity unique IDs remain byte-for-byte stable.

### Runtime and privacy

- Cloud and self-hosted clients use the same parsers and coordinators;
- dashboard URLs use the configured dashboard origin or remain absent;
- manifest reports `local_polling`;
- diagnostics expose deployment class and CA presence only;
- tokens, URLs, addresses, certificates, response payloads, and identifiers are
  absent from diagnostics and captured logs;
- all existing Cloud, routing, lifecycle, repository, HACS, and hassfest gates
  remain green.

## Live validation gate

Public self-hosted support is not complete from mocks alone. Before release,
run a protected manual GET-only validation against a disposable or explicitly
approved self-hosted instance with:

- the exact NetBird version recorded;
- HTTPS and PAT authentication;
- at least one peer and one Network with Resources and Routers;
- one setup/reload/poll cycle in Home Assistant;
- one same-account PAT reauth;
- one same-account endpoint/dashboard reconfigure;
- one invalid redirect/TLS case proving fail-closed behavior;
- private-CA coverage if the release claims private-CA support.

The run must log only fixed pass/fail capability names. It must not retain the
PAT, URL, certificate, identifiers, response bodies, diagnostics, or private
addresses. Frontend screenshots and installation evidence remain separate
evidence classes.

## Rollout and rollback

1. Implement ROD-48 behind explicit deployment selection while preserving the
   Cloud default.
2. Merge only after the full local Linux gate and hosted CI pass.
3. Complete the protected self-hosted live gate before changing public support
   claims or publishing the release.
4. If runtime evidence fails, keep the release Cloud-only and leave ROD-48 open;
   do not weaken TLS, redirects, schemas, or availability to force a pass.
5. Roll back code by reverting ROD-48. Version-3 Cloud entries remain readable
   only by code that understands the deployment field, so users must restore a
   Home Assistant backup when downgrading across the config-entry migration.

## Acceptance and stop condition

ROD-36 is complete when this document is approved with no unresolved decisions.
ROD-48 may then start and is complete only when:

- every automated requirement above passes;
- existing Cloud entries migrate without registry churn;
- the protected live self-hosted gate passes with recorded version and scope;
- EN/UK documentation states the exact URL, TLS, CA, redirect, compatibility,
  and reachability boundaries;
- no PAT, private URL, certificate, payload, or identifier appears in logs,
  diagnostics, CI, or artifacts.

The implementation stops there. MSP, OAuth, HTTP, mTLS, discovery, subpath
hosting, dynamic IoT classes, version allowlists, and reachability testing
require separate evidence and issues.
