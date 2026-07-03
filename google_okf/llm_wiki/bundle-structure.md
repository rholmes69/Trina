---
type: Reference
title: Bundle Structure
description: Directory layout, reserved filenames, and distribution options for an OKF bundle.
tags: [okf, bundle, structure, directory]
timestamp: 2026-07-02T00:00:00Z
---

A **bundle** is a directory tree of markdown files. The directory structure is independent of the domain — producers organize concepts however makes sense for the knowledge being captured.

## Directory Layout

```
path/to/bundle/
├── index.md                      # Optional. Directory listing for progressive disclosure.
├── log.md                        # Optional. Chronological history of updates.
├── <concept>.md                  # A concept at the bundle root.
└── <subdirectory>/               # Subdirectories organize concepts into groups.
    ├── index.md
    ├── <concept>.md
    └── <subdirectory>/
        └── …
```

There is no enforced structure beyond the reserved filenames. Producers choose their own hierarchy.

## Reserved Filenames

These filenames have defined meaning at any level of the hierarchy and MUST NOT be used for concept documents:

| Filename | Purpose |
|----------|---------|
| `index.md` | Directory listing for progressive disclosure. See [reserved-files](reserved-files.md). |
| `log.md` | Chronological update history. See [reserved-files](reserved-files.md). |

All other `.md` files are concept documents.

## Distribution Options

A bundle MAY be distributed as:

- A **git repository** (recommended — provides history, attribution, diffs).
- A **tarball or zip archive** of the directory.
- A **subdirectory** within a larger repository.

Git is preferred because it provides authorship, diffs, and chronological history for free — complementing the optional [log.md](reserved-files.md) convention.

# Citations

[1] [OKF Specification v0.1 §3](../spec.md)
