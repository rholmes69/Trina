---
type: Reference
title: Cross-Linking
description: How OKF concepts reference each other using standard markdown links.
tags: [okf, links, relationships, graph]
timestamp: 2026-07-02T00:00:00Z
---

Concepts MAY link to other concepts using standard markdown links. Links express relationships between concepts and form the edges of the bundle's knowledge graph.

## Link Forms

### Absolute (bundle-relative) links — Recommended

Begin with `/`, interpreted relative to the bundle root.

```markdown
See the [customers table](/tables/customers.md) for the join key.
```

Preferred because the link remains stable when documents move within their subdirectory.

### Relative links

Standard markdown relative paths.

```markdown
See the [neighboring concept](./other.md).
```

Useful for tightly coupled concepts in the same directory.

## Link Semantics

A link from concept A to concept B asserts a **relationship**. The specific kind of relationship (references, joins-with, depends-on, child-of, etc.) is conveyed by the surrounding prose, not the link itself.

Consumers that build a graph view treat all links as **directed edges of an untyped relationship**.

## Broken Links

Consumers MUST tolerate broken links — a link whose target does not exist in the bundle is **not malformed**. It may represent not-yet-written knowledge, a concept from another bundle, or a planned future document.

# Citations

[1] [OKF Specification v0.1 §5](../spec.md)
