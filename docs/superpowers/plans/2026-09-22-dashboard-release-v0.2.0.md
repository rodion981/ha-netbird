# NetBird Dashboard and v0.2.0 Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the weak dashboard example with a native dynamic dashboard, document the useful monitoring model in both languages, and publish a verified v0.2.0 release.

**Architecture:** Use one standard Home Assistant Markdown card whose Jinja template discovers entities through `integration_entities("netbird")` and the stable `netbird_key` attribute. Update release metadata only after peer and topology gates pass. Publish from an annotated tag after tag CI succeeds.

**Tech Stack:** Home Assistant Markdown card/Jinja, YAML, Markdown, GitHub Actions, HACS/hassfest.

**Spec:** `docs/superpowers/specs/2026-09-22-netbird-v0.2.0-monitoring-design.md`

## Global Constraints

- Dashboard uses no generated entity IDs and no third-party cards.
- Dashboard must distinguish unavailable, unknown, false, and zero.
- English and Ukrainian README content must stay equivalent.
- Release remains Cloud-only and read-only.
- Publish only after local and tag CI gates pass.

## Review Focus

- Empty installations render readable empty tables instead of broken Jinja.
- Localized entity IDs do not affect dashboard discovery.
- Disabled optional entities render an em dash without template errors.
- Resource addresses and peer IPs are documented as Recorder-visible data.
- The release tag points at the exact commit that passed tag CI.

---

### Task 1: Replace the dashboard with native entity discovery

**Files:**
- Modify: `examples/netbird-dashboard.yaml`
- Modify: `tests/test_repository_quality.py`
- Create: `tests/test_dashboard_example.py`

**Interfaces:**
- Consumes: `netbird_key` attributes from peer and topology entities.
- Produces: one dependency-free Home Assistant dashboard.

- [ ] **Step 1: Add failing dashboard contract tests**

```python
dashboard = yaml.safe_load((ROOT / "examples/netbird-dashboard.yaml").read_text())
source = (ROOT / "examples/netbird-dashboard.yaml").read_text()
assert "custom:auto-entities" not in source
assert 'integration_entities("netbird")' in source
assert "netbird_key" in source
assert "Peers" in source
assert "Networks" in source
assert "Network resources" in source
```

Add Home Assistant template-rendering cases for:

- no NetBird entities;
- arbitrary localized entity IDs carrying stable `netbird_key` attributes;
- a peer with unavailable and absent optional entities;
- populated peer, network, and resource devices.

- [ ] **Step 2: Run and confirm failure**

Run: `wsl.exe -e bash -lc 'cd /mnt/d/Dev/ha-netbird && uv run pytest -q tests/test_repository_quality.py tests/test_dashboard_example.py'`

- [ ] **Step 3: Implement the native Markdown dashboard**

Use a Markdown card with a template beginning:

```yaml
type: markdown
content: |-
  {% set netbird_entities = integration_entities("netbird") %}
  {% set peer_connections = namespace(items=[]) %}
  {% for entity_id in netbird_entities %}
    {% if state_attr(entity_id, "netbird_key") == "connected" %}
      {% set peer_connections.items = peer_connections.items + [entity_id] %}
    {% endif %}
  {% endfor %}
```

For each connection entity, obtain the device with `device_id(entity_id)`, inspect `device_entities(device)`, and resolve values by `netbird_key`. Render peer, network, and resource Markdown tables. Use `unknown` and `unavailable` guards before converting values.

- [ ] **Step 4: Parse YAML and inspect template tokens**

Run: `wsl.exe -e bash -lc 'cd /mnt/d/Dev/ha-netbird && uv run pytest -q tests/test_repository_quality.py tests/test_dashboard_example.py'`

Expected: PASS.

- [ ] **Step 5: Commit the dashboard**

```bash
git add examples/netbird-dashboard.yaml tests/test_repository_quality.py tests/test_dashboard_example.py
git commit -m "docs: add native dynamic NetBird dashboard"
```

### Task 2: Update documentation, privacy text, and release metadata

**Files:**
- Modify: `README.md`
- Modify: `README.uk.md`
- Modify: `CHANGELOG.md`
- Modify: `custom_components/netbird/manifest.json`
- Modify: `pyproject.toml`
- Modify: `tests/test_repository_quality.py`

**Interfaces:**
- Consumes: final peer/topology behavior.
- Produces: accurate v0.2.0 public documentation and version metadata.

- [ ] **Step 1: Add failing metadata assertions**

```python
assert manifest["version"] == "0.2.0"
assert project["project"]["version"] == "0.2.0"
assert "auto-entities" not in readme.lower()
assert "Networks" in readme
assert "Networks" in readme_uk
```

- [ ] **Step 2: Update both README files**

Document every enabled and disabled entity, five-minute topology polling, `1 + 2N` request cost, partial availability, deprecated Routes exclusion, dashboard installation, and Recorder visibility of IP/resource states.

- [ ] **Step 3: Add v0.2.0 changelog and bump versions**

Set both project and manifest versions to `0.2.0`. Add a changelog section listing peer monitoring, Networks/Resources/Routers, migration, and the native dashboard.

- [ ] **Step 4: Run repository contracts**

Run: `wsl.exe -e bash -lc 'cd /mnt/d/Dev/ha-netbird && uv run pytest -q tests/test_repository_quality.py'`

- [ ] **Step 5: Commit release documentation**

```bash
git add README.md README.uk.md CHANGELOG.md custom_components/netbird/manifest.json pyproject.toml tests/test_repository_quality.py
git commit -m "docs: prepare NetBird v0.2.0 release"
```

### Task 3: Run the complete release gate

**Files:**
- No product changes expected unless a gate identifies a defect.

- [ ] **Step 1: Synchronize the locked environment**

Run: `wsl.exe -e bash -lc 'cd /mnt/d/Dev/ha-netbird && uv sync --frozen'`

- [ ] **Step 2: Run all local quality gates**

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest -q --cov=custom_components.netbird --cov-report=term-missing --cov-fail-under=95
```

- [ ] **Step 3: Scan source and complete Git history**

```bash
gitleaks dir --redact=100 --no-banner .
gitleaks git --redact=100 --no-banner .
```

- [ ] **Step 4: Push main and wait for quality, hassfest, and HACS jobs**

Run: `git push origin main`

Expected: all three GitHub Actions jobs complete successfully.

### Task 4: Publish v0.2.0

**Files:**
- No source changes.

- [ ] **Step 1: Create and push an annotated tag**

```bash
git tag -a v0.2.0 -m "NetBird for Home Assistant v0.2.0"
git push origin v0.2.0
```

- [ ] **Step 2: Wait for tag CI**

Expected: quality, hassfest, and HACS all pass on the exact tagged commit.

- [ ] **Step 3: Publish bilingual GitHub release notes**

Release notes must summarize peer entities, Networks/Resources/Routers, migration behavior, dashboard replacement, Cloud-only scope, privacy/Recorder implications, and upgrade instructions.

- [ ] **Step 4: Verify public release state**

Confirm the release is public and marked Latest, the tag resolves to the tested commit, the repository working tree is clean, and the HACS install link still targets `rodion981/ha-netbird`.
