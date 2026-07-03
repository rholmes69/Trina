---
type: Reference
title: Reserved Files — index.md and log.md
description: Structure and purpose of the two reserved filenames in an OKF bundle.
tags: [okf, index, log, reserved]
timestamp: 2026-07-02T00:00:00Z
---

Two filenames are reserved at any level of the bundle hierarchy. They MUST NOT be used for concept documents.

## index.md — Directory Listing

An `index.md` file supports **progressive disclosure** — letting a human or agent see what is available before opening individual documents.

### Structure

Index files contain **no frontmatter** (exception: a bundle-root `index.md` may include `okf_version` frontmatter for version declaration).

The body groups concepts under headings using a bullet-link format:

```markdown
# Section / Group Heading

* [Title 1](relative-url-1) - short description of item 1
* [Title 2](relative-url-2) - short description of item 2

# Another Section

* [Subdirectory](subdir/) - short description of the subdirectory
```

### Rules

- Entries SHOULD include the description from the linked concept's frontmatter.
- Producers MAY generate `index.md` automatically.
- Consumers MAY synthesize one on the fly when none is present.
- `index.md` is optional at every level — its absence does not make a bundle non-conformant.

---

## log.md — Update History

A `log.md` file records the history of changes to that scope of the bundle. Format is a flat list of date-grouped entries, newest first.

### Structure

```markdown
# Directory Update Log

## 2026-05-22

* **Update**: Added new BigQuery table reference for [Customer Metrics](/tables/customer-metrics.md).
* **Creation**: Established the [Dataplex Playbook](/playbooks/dataplex.md).

## 2026-05-15

* **Initialization**: Created foundational directory structure.
```

### Rules

- Date headings MUST use ISO 8601 `YYYY-MM-DD` format.
- Log entries are prose. The leading bold word (`**Update**`, `**Creation**`, `**Deprecation**`) is a **convention**, not a requirement.
- `log.md` is optional at every level.

# Citations

[1] [OKF Specification v0.1 §6–7](../spec.md)
