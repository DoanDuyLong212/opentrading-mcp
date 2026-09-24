---
name: web-research
description: Use when the agent needs up-to-date information from the web — search first, then fetch results recursively, following redirects across hosts.
---

# Web Research

## Overview
Discipline for `web_search` + `web_fetch`: search before fetching, read every
result, follow relevant links recursively until the information need is met.

## When to Use
- Any question needing facts beyond the knowledge cutoff or local data
- Verifying library docs, API references, or market news before acting
- When NOT to use: data already covered by vn/vs/dnse/yf market tools

## Core Pattern
1. `web_search` with a precise query first (never guess a URL).
2. `web_fetch` each promising result (markdown default).
3. If a fetch reveals relevant links, fetch those too — recurse until done.
4. If a fetch reports a redirect to a different host, immediately fetch the
   redirect URL instead.

## Quick Reference
| Situation | Action |
|---|---|
| Need background facts | `web_search{query, numResults: 8}` |
| Read a result | `web_fetch{url, format: "markdown"}` |
| Page needs exact markup | `web_fetch{url, format: "html"}` |
| Plain-text extraction | `web_fetch{url, format: "text"}` |
| `web_search` missing from tools/list | No provider key set (`EXA_API_KEY`/`PARALLEL_API_KEY`) — not an error |

## Env
| Variable | Meaning |
|---|---|
| `EXA_API_KEY` | Enables Exa provider |
| `PARALLEL_API_KEY` | Enables Parallel provider |
| `WEBSEARCH_PROVIDER` | `exa` \| `parallel` \| unset (auto A/B by query hash) |
