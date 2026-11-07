# M09 implementation report

Base: `21b9ca4`. Initial `git status --short` was clean. No commit created.

## Baseline

- Python 3.13.5, pytest 9.0.2, NumPy 2.4.4, Playwright installed locally.
- No template test files existed at baseline; the planned test command reported `file or directory not found: tests/management/test_templates.py` and ran no tests.

## Delivered

- Added a durable `TemplateRegistry` stored under the configured management data directory. Each save appends an immutable version with a template schema version, canonical supported draft, resolved configuration hash, capability revision, name and timestamp. Saves use atomic file replacement and restore the in-memory state if persistence fails.
- Added template list, inspect, exact-version, and load endpoints. Loading requires the exact supported draft field set and canonical values; it re-resolves the stored draft and rejects changed capability revisions, changed scenario content, unavailable capabilities, and schema drift without normalizing the saved data.
- Extra draft fields, including credential-like keys, are rejected and never persisted. Template payloads only retain the supported non-secret draft fields.
- Added template selection, inspect and load controls plus saving reviewed drafts as new template versions. Applying over a modified draft asks before replacement. A loaded template is revalidated and previewed before launch.
- Runs created from a template store template ID/version, the source version's configuration hash and capability revision, and the launch configuration hash. Later template versions do not change earlier run provenance. The source reference is verified against the current compatible stored version at run creation.
- The UI and report explain that templates reproduce configuration and do not restore world state like checkpoints.

## Verification

Planned command:

```text
python3 -m pytest -q tests/management/test_templates.py tests/management/test_templates_browser.py
8 passed in 4.42s
```

Additional regression command:

```text
python3 -m pytest -q tests/management/test_templates.py tests/management/test_templates_browser.py tests/management/test_runs.py tests/management/test_drafts.py tests/management/test_new_run_browser.py
48 passed in 20.68s
```

Coverage includes immutable versions and reload, schema/canonical-form and stale-capability rejection, secret-field rejection, rollback after persistence failure, API list/inspect/load, browser dirty-draft cancel/confirm behavior, preview before launch, run provenance retained after a newer version is saved, and existing run/draft/browser regressions.
