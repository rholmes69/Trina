---
type: Reference
title: Citations
description: How to cite external sources within OKF concept bodies.
tags: [okf, citations, sources]
timestamp: 2026-07-02T00:00:00Z
---

When a concept's body makes claims sourced from external material, those sources SHOULD be listed under a `# Citations` heading at the bottom of the document, numbered.

## Format

```markdown
# Citations

[1] [BigQuery public dataset announcement](https://cloud.google.com/blog/...)
[2] [Internal data quality runbook](https://wiki.acme.internal/data/quality)
```

## Link Types

Citation links MAY be:

- **Absolute URLs** — external web resources.
- **Bundle-relative paths** — other concepts within the same bundle.
- **Paths into a `references/` subdirectory** — external material mirrored as first-class OKF concepts.

## Placement

Citations appear at the **bottom** of the concept body, after all other content, under the `# Citations` heading.

# Citations

[1] [OKF Specification v0.1 §8](../spec.md)
