# Manual live API contract

The `Live API contract` GitHub Actions workflow checks current NetBird Cloud response shapes without saving or printing live data. It runs only through `workflow_dispatch` and uses read-only `GET` requests.

## Required disposable account

Prepare a disposable NetBird Cloud account containing:

- at least one peer assigned to a group;
- at least one Network;
- at least one resource;
- at least one group-based Network router.

The coverage requirements prevent an empty account from producing misleading success.

## Protected environment

In repository settings, create the `netbird-live-contract` Environment:

1. Add at least one required reviewer.
2. For this single-maintainer repository, use `rodion981` as the reviewer and leave prevention of self-review disabled. Independent review remains preferable when another trusted maintainer becomes available.
3. Restrict deployment branches to `main`.
4. Add `NETBIRD_LIVE_API_TOKEN` only as an Environment secret.
5. Do not create repository or organization secrets with the same name.

The PAT needs read access only for accounts, peers, Networks, resources, and routers. Revoke it after the disposable-account validation if it is no longer needed.

## Evidence boundary

Run the workflow manually and approve the protected Environment job. Retain only the workflow run URL and final result. Do not copy payloads, logs containing account data, identifiers, names, addresses, or URLs into issues or repository files.

Success output contains only the result, integration version, unversioned Cloud API context, and contract revision. Failures contain only a fixed code. The workflow does not upload artifacts, use caches, save fixtures, run on pull requests, run on pushes, or run on a schedule.

## Recorded evidence

The protected [manual run on 25 September 2026](https://github.com/rodion981/ha-netbird/actions/runs/36159603786/job/108170984157) passed for the complete v0.2.0 endpoint and peer-group shape. The temporary group-router coverage object and disposable PATs were removed afterward. This records point-in-time API-shape evidence only; it does not establish continuous production, installation, frontend, reachability, or VPN-path behavior.
