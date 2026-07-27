# Security policy

## Reporting a vulnerability

Use the repository's **Security** tab to open a private security advisory. Do not publish an
exploit, private study material, local paths, credentials, or model files in a public issue.

Include:

- the affected commit or release;
- the smallest reproducible input that contains no personal data;
- expected and observed behavior;
- impact and any known workaround.

## Security boundaries

The supported runtime:

- uses separate Windows and POSIX launchers and rejects the wrong launcher before side effects;
- resolves symlinks and junctions before accepting study inputs from inside the repository;
- deliberately rejects every reparse point in Windows launchers, while Python/POSIX code resolves
  links and accepts them only when the final target remains inside the repository;
- writes only inside the configured repository-local data home;
- passes decoded NumPy arrays, not URLs, to RapidOCR;
- supplies and hashes fixed local ONNX models before OCR;
- treats the pinned RapidOCR package model layout as part of the verified dependency contract and
  stops if that layout or any expected model path changes;
- rechecks model hashes on cache hits and aborts immediately on any mismatch;
- neutralizes spreadsheet formulas in CSV reports;
- disables pypdf's optional external JBIG2 decoder;
- does not create accounts, scheduled tasks, global links, or global packages.

Treat the local learning database and imports as sensitive personal data. They are excluded by
`.gitignore`, but contributors must still inspect staged files before every commit.
