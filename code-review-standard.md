# Code review standard

## Review levels

- **L1 self-review:** the author runs every local quality gate, reviews the diff, and confirms
  that no private learning data or generated runtime files are staged.
- **L2 peer review:** at least one peer approves correctness, tests, maintainability, and user
  impact. L2 approval is required before merge.
- **L3 senior review:** required for security boundaries, database migrations, FSRS behavior,
  public interfaces, dependency changes, OCR model hashes, and backup or deletion logic.

## Definition of Done

A change is mergeable only when:

1. acceptance criteria and failure behavior are documented;
2. tests cover the normal path and at least one relevant failure path;
3. Windows and Linux CI pass;
4. lint, formatting, type checking, secret scanning, SAST, and coverage gates pass;
5. security-sensitive behavior fails closed;
6. migrations preserve existing history and include an upgrade test;
7. user-facing Skill instructions and references match deterministic scripts;
8. no private data, generated files, credentials, or machine-specific paths are committed.

## Review labels and comment format

- 🔴 **Blocking:** security, data loss, correctness, privacy, or incompatible public behavior.
- 🟡 **Should fix:** robustness, maintainability, performance, or missing edge-case coverage.
- 💭 **Suggestion:** optional improvement that does not block merge.

Use: `[label] Short title — evidence, impact, and a concrete requested change`.

## Five review dimensions

- **Correctness:** invariants, scoring, FSRS calls, migrations, edge cases, and regression tests.
- **Security:** path confinement, formula injection, untrusted files, secrets, hashes, and
  fail-closed behavior.
- **Robustness:** transactions, JSON errors, crash recovery, limits, backup verification, and
  cross-platform behavior.
- **Maintainability:** focused modules, clear names, useful types, concise Skill instructions,
  and limited duplication.
- **Performance:** bounded input sizes, OCR caching, memory use, database indexes, and avoidance
  of unnecessary image/model work.

## Cross-platform and path-boundary requirements

- Never construct containment prefixes, virtual-environment executables, or child paths with
  literal `/` or `\` separators in code intended for more than one operating system. Use the
  platform path API or separate, explicitly platform-scoped launchers.
- A platform-scoped launcher must reject unsupported operating systems before creating files,
  changing environment variables, or invoking package installers.
- String-prefix checks alone are never proof of containment. Normalize `..` and absolute paths,
  then resolve symlinks or reject every existing symlink, junction, or reparse-point component
  before a read or write. Boundary failures must fail closed.
- Every path-boundary change needs automated tests for a safe child, `..` traversal, an absolute
  outside path, and a symlink or junction escape on each supported platform.
- Every SQLite business write must acquire `BEGIN IMMEDIATE` before reading mutable state, use a
  bounded busy timeout, and have a two-writer contention test. Read-only commands must not perform
  schema-version writes when no migration is needed.

## Required automated gates

Run Ruff lint and format checks, mypy, detect-secrets, Bandit, branch coverage, release privacy
validation, Skill validation, and unit tests. Coverage must remain at or above the threshold in
CI; lowering it requires L3 approval and a written reason.

## Quality metrics

Track median review turnaround, escaped defects, percentage of 🔴 findings resolved before
merge, flaky-test rate, and coverage trend. Review the metrics monthly without ranking
individual contributors.
