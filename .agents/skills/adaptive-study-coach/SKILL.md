---
name: adaptive-study-coach
description: Import daily study material and run adaptive spaced-repetition learning for English vocabulary or any academic subject. Use when the user wants to recognize or add words or knowledge from chat, blurry screenshots, phone photos, scans, TXT, Markdown, CSV, Excel, JSON, or PDF; clean and OCR a study image locally; reduce image-reading tokens; adapt to the computer; start an FSRS review; repair wrong answers with same-concept variants; take a weekly or monthly test; inspect progress; or back up and check learning data.
---

# Adaptive Study Coach

Operate the repository-local learning system. Derive the workspace from the `.agents` directory
containing this skill. Keep every created file inside that workspace. The default data home is
`<workspace>/adaptive-study-data`; `ADAPTIVE_STUDY_HOME` may select another directory inside
the same workspace.

Do not create global skill links, scheduled tasks, external accounts, or files outside the
workspace.

## Run the deterministic manager

Resolve the launcher relative to this file and use it for every data operation:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "<skill-root>\scripts\run-study.ps1" <command> <arguments>
```

On Linux or macOS, run:

```bash
bash "<skill-root>/scripts/run-study.sh" <command> <arguments>
```

Run `health` first. If the local runtime is missing, tell the user to run the repository-level
`scripts/setup.ps1` on Windows or `scripts/setup.sh` elsewhere; do not install globally. Run
`init` only if the database is absent. Require one valid JSON object from every manager call. If
output is empty or non-JSON, do not infer success: run `health` once, preserve the database, and
report the diagnostic. Explain valid JSON results in the user's language.

## Route the request

- Import material: read [import-schema.md](references/import-schema.md), normalize the source,
  save intermediate JSON under the `imports` directory returned by the manager, then run
  `import`.
- Photo, screenshot, or scanned image: read
  [image-ingestion.md](references/image-ingestion.md), run `image-prepare --file <local-image>`,
  and follow `token_strategy.route`. Read OCR text before opening an image.
- Daily review: run `session-start --kind daily`. It resumes the latest active daily session,
  including one started on an earlier date. Ask returned items one at a time.
- Weekly or monthly test: run `session-start --kind weekly` or `monthly`. Use the returned order
  and never reveal answers before the first response.
- Progress: run `dashboard` and summarize due work, accuracy, weak topics, and test status.
- Data safety: run `backup` or `health`.
- Pending OCR or incomplete entries: run `pending`; resolve them with `pending-resolve`.

## Import accurately

Pass structured TXT, Markdown, CSV, Excel, JSON, or text PDF directly to `import`. For a photo or
screenshot, always run local `image-prepare` first. It corrects orientation, perspective, small
skew, uneven lighting, contrast, and mild blur without generative reconstruction, then runs
hash-pinned local OCR. For a scanned PDF, render only the needed page to an image inside the
workspace before using the same route.

Use progressive disclosure:

- High confidence: read `ocr.txt` only.
- Medium confidence: inspect `primary.png` only if text remains ambiguous.
- Low confidence: inspect only the smallest retry tile covering the ambiguity.

Never open the original and every derivative by default. Reuse the content-addressed cache for
identical images.

Extract only visible facts, then create normalized JSON. Keep `ocr_confidence` separate from
`content_confidence`. OCR confidence measures transcription clarity only and must never authorize
automatic import. Set `content_verified: true` only after a person confirms the prompt-answer
pair. Route unverified OCR, unclear characters, formulas, tables, answerless items, and unresolved
conflicts to pending. A common dictionary meaning for an English word may be supplied from model
knowledge only when labeled `source: "model-assisted"` and `content_confidence` is at most `0.85`.

Import complete non-OCR entries at `content_confidence >= 0.75`. Import OCR-derived entries only
when they also have `content_verified: true`. Let the manager enforce these rules and report
imported, duplicate, and pending counts.

## Conduct a review

Read [learning-protocol.md](references/learning-protocol.md) before the first review or test in a
task.

1. Start the session and keep its `session_id`.
2. Ask exactly one question at a time. Accept listed aliases and clearly equivalent wording.
3. Record the first attempt:
   - wrong or no recall: `answer --result again`
   - correct but prompted or visibly hesitant: `answer --result hard`
   - correct: `answer --result good`
   - explicitly effortless: `answer --result easy`
4. After a first-attempt error, explain briefly and ask a different question about the same
   knowledge point. Record each variant with `answer --remediation`. Continue until correct or
   until the manager returns `remediation_exhausted`. Never call FSRS again for remediation.
5. When remediation is exhausted, show the correct answer, mark it unresolved for future FSRS
   review, and move on. Never bypass either the per-item or per-session hard limit.
6. For a daily session, stop near 20 minutes but finish or exhaust the active remediation chain.
   Run `session-finish`; do not postpone unseen due items.

The manager preserves the first `Again` rating after remediation succeeds. Never edit history to
make performance look better.

## Conduct tests

Weekly tests use about 12 questions and 15 minutes. Monthly tests use about 30 questions and
30 minutes. Score only first attempts. Apply the same bounded remediation rule after each
mistake. Test attempts update FSRS through the pinned Py-FSRS library. Finish the session to
generate Markdown and spreadsheet-safe CSV reports and a database backup.

## Preserve data

Treat `<data-home>\data\study.db` as the source of truth. Do not delete or rewrite database
history. Use transactional manager commands and SQLite backup operations. The manager serializes
competing writers with `BEGIN IMMEDIATE`; if another task is updating the database, show the
returned retry message instead of bypassing the lock. Do not remove old backups manually. Let the
manager verify each backup with SQLite integrity checking and SHA-256, then apply the configured
count and total-size retention limits.

The image pipeline accepts local image files inside the workspace only. Pass NumPy arrays to
RapidOCR, explicitly set all three bundled ONNX model paths, and verify their SHA-256 hashes
before inference. Do not call RapidOCR URL input or download helpers. Keep enhanced images, OCR
text, manifests, retry tiles, caches, and temporary files under the data home.

Read [design-sources.md](references/design-sources.md) only for learning-design provenance. Read
[image-design-sources.md](references/image-design-sources.md) for image/OCR provenance and
security decisions.
