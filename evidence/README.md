# Evidence

The files here separate deterministic checks from judgments about arguments.

- `submission-checks-2026-10-29.json` records the release-day complete offline suite and smoke workflow: 115 passed, one Windows privilege-related skip, no failures/errors and no API calls. The October 21 evidence below retains its original date and scope.

- `reliability-checks-2026-10-21.json` records the current complete offline suite: 115 passed, one Windows privilege-related skip, and the report/adapter/partial-failure regressions. Preserved live responses were replayed for release compatibility; no new inference occurred. Earlier dated evidence below retains its original scope.

- `FILE-MANIFEST.json` lists the current package files and SHA-256 hashes, excluding itself.
- `source-grounding-checks.json` records the October 20 documentation checks: source counts, local links, criterion preservation, and unchanged executable files.
- `SOURCE-REGISTER.json` records the bibliography's verified identities, reading scopes, and bounded conceptual mappings.
- `offline-checks.json` retains the October 19 scoped software checks: 49 tests passed, with the 48 section-trial tests explicitly deferred. It is not a fresh full-suite result.
- `newcomer-dry-run.json` and `contamination-checks.json` retain the earlier offline workflow and package-content checks.

The October 20 work used public bibliographic lookups and local source reading. It made no paid API/model calls and ran no private-paper evaluation. Source verification does not validate semantic judgments or diagnostic accuracy.
