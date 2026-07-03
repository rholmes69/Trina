---
type: Reference
title: Concept Documents
description: Structure, frontmatter fields, body conventions, and examples for OKF concept documents.
tags: [okf, concept, frontmatter, markdown]
timestamp: 2026-07-02T00:00:00Z
---

Every concept is a UTF-8 markdown file with two parts:

1. A **YAML frontmatter block** — delimited by `---` at the top of the file.
2. A **markdown body** — free-form content after the frontmatter.

## Frontmatter Fields

```yaml
---
type: <Type name>                  # REQUIRED
title: <Optional display name>
description: <Optional one-line summary>
resource: <Optional canonical URI for the underlying asset>
tags: [<tag>, <tag>, …]
timestamp: <ISO 8601 datetime>
# … any additional producer-defined key/value pairs
---
```

### Required Fields

| Field | Description |
|-------|-------------|
| `type` | Identifies the kind of concept. Used by consumers for routing, filtering, presentation. E.g. `BigQuery Table`, `API Endpoint`, `Playbook`, `Reference`. **Not registered centrally** — choose descriptive values. |

Consumers MUST tolerate unknown `type` values by treating them as generic concepts.

### Recommended Fields

| Field | Description |
|-------|-------------|
| `title` | Human-readable display name. If omitted, consumers may derive from filename. |
| `description` | Single sentence summary. Used in index snippets and search previews. |
| `resource` | URI of the underlying asset (e.g. a BigQuery table URL). Omit for abstract concepts. |
| `tags` | YAML list of short strings for cross-cutting categorization. |
| `timestamp` | ISO 8601 datetime of last meaningful change. |

### Extensions

Producers MAY add any additional keys. Consumers SHOULD preserve unknown keys when round-tripping and MUST NOT reject documents with unrecognized fields.

## Body Conventions

The body is standard markdown. Favor **structural markdown** (headings, lists, tables, fenced code blocks) over freeform prose — structure aids both human reading and agent retrieval.

### Conventional Section Headings

| Heading | Purpose |
|---------|---------|
| `# Schema` | Structured description of an asset's columns or fields. |
| `# Examples` | Concrete usage examples, often as fenced code blocks. |
| `# Citations` | External sources backing claims in the body. See [citations](citations.md). |

These headings have **conventional** meaning and SHOULD be used when applicable. No other sections are required.

## Examples

### Concept bound to a resource

```markdown
---
type: BigQuery Table
title: Customer Orders
description: One row per completed customer order across all channels.
resource: https://console.cloud.google.com/bigquery?p=acme&d=sales&t=orders
tags: [sales, orders, revenue]
timestamp: 2026-05-28T14:30:00Z
---

# Schema

| Column        | Type      | Description                              |
|---------------|-----------|------------------------------------------|
| `order_id`    | STRING    | Globally unique order identifier.        |
| `customer_id` | STRING    | FK into [customers](/tables/customers.md). |
| `total_usd`   | NUMERIC   | Order total in US dollars.               |
| `placed_at`   | TIMESTAMP | When the customer submitted the order.   |
```

### Concept not bound to a resource (abstract)

```markdown
---
type: Playbook
title: Incident response — data freshness alert
description: Steps to triage a freshness alert on the orders pipeline.
tags: [oncall, incident]
timestamp: 2026-04-12T09:00:00Z
---

# Trigger

A freshness alert fires when `orders` lags more than 30 minutes behind its expected SLA.

# Steps

1. Check the ingestion job dashboard.
2. …
```

# Citations

[1] [OKF Specification v0.1 §4](../spec.md)
