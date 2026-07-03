---
type: Reference
title: Versioning
description: OKF version numbering scheme, compatibility rules, and how bundles declare their target version.
tags: [okf, versioning, compatibility]
timestamp: 2026-07-02T00:00:00Z
---

OKF uses `<major>.<minor>` versioning. The current version is **0.1**.

## Version Bump Rules

| Bump | Meaning |
|------|---------|
| **Minor** | Backward-compatible additions — new optional fields, new conventional section headings. |
| **Major** | Breaking changes — renaming required fields, changing reserved filenames. |

## Declaring a Version in a Bundle

Bundles MAY declare their target OKF version by including `okf_version` in the bundle-root `index.md` frontmatter block. This is the **only** place frontmatter is permitted in an `index.md`.

```markdown
---
okf_version: "0.1"
---

# My Bundle Index

* [Concept A](concept-a.md) - Description of A
```

## Consumption Behavior

Consumers that do not understand the declared version SHOULD attempt **best-effort consumption** rather than refusing the bundle. Unknown fields and unknown types must be tolerated (see [conformance](conformance.md)).

# Citations

[1] [OKF Specification v0.1 §11](../spec.md)
