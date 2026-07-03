---
type: Reference
title: OKF Overview
description: What OKF is, its design principles, goals, and non-goals.
tags: [okf, overview, format]
timestamp: 2026-07-02T00:00:00Z
---

OKF (Open Knowledge Format) is an open, human- and agent-friendly format for representing **knowledge** — the metadata, context, and curated insight that surrounds data and systems.

It is a directory of markdown files with YAML frontmatter. No schema registry, no central authority, no required tooling. If you can `cat` a file, you can read OKF.

## Design Principles

- **Readable** by humans without tooling.
- **Parseable** by agents without bespoke SDKs.
- **Diffable** in version control.
- **Portable** across tools, organizations, and time.

The format is minimally opinionated. It standardizes only the small set of structural conventions needed to make a knowledge corpus **self-describing**. Everything beyond that is left to the producer.

## Goals

1. Define a universal format that **enrichment agents** can write into.
2. Inform how **consumption agents** should read and traverse it.
3. Facilitate **exchange** of knowledge across systems and organizations.
4. Standardize the small number of **required** fields that must be present for content to be meaningfully consumed.

## Non-Goals

- Defining a fixed taxonomy of concept types.
- Prescribing storage, serving, or query infrastructure.
- Replacing domain-specific schemas (Avro, Protobuf, OpenAPI, etc.) — OKF *references* them; it does not subsume them.

## Relationship to Other Formats

OKF is intentionally close to:

- **LLM wiki repositories** — markdown + frontmatter as agent-readable knowledge bases.
- **Personal knowledge tools** — Obsidian, Notion: hierarchical markdown with cross-links.
- **"Metadata as code"** — catalog metadata stored alongside source code.

OKF differs primarily in being **specified** — pinning down the small set of rules needed for interoperability without dictating tooling.

## Key Terminology

| Term | Definition |
|------|------------|
| **Knowledge Bundle** | A self-contained, hierarchical collection of knowledge documents. The unit of distribution. |
| **Concept** | A single unit of knowledge. One markdown file. |
| **Concept ID** | The file path within the bundle, minus `.md`. E.g. `tables/users`. |
| **Frontmatter** | YAML block delimited by `---` at the top of a file. |
| **Body** | Everything after the frontmatter. |
| **Link** | A standard markdown link from one concept to another. |
| **Citation** | A link from a concept to an external source. |

# Citations

[1] [OKF Specification v0.1](../spec.md)
