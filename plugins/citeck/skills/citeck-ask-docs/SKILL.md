---
name: citeck-ask-docs
description: "Ask a question about the Citeck ECOS platform — searches citeck-docs via RAG and synthesizes an answer with citations. Use when the user asks how Citeck works, how to configure something, or about platform concepts."
allowed-tools: mcp__citeck__search_docs, mcp__citeck__set_docs_profile, AskUserQuestion
---

# Ask Citeck Documentation

Answer questions about the Citeck ECOS platform using semantic search over the citeck-docs repository, then synthesize a concise answer grounded in the retrieved snippets.

## Prerequisites

Run `/citeck:citeck-auth` first so at least one profile has credentials. The docs RAG service is reached via the profile set as `docs_profile` in `~/.citeck/credentials.json` (falls back to the active profile).

## Flow

### Step 1: Get the question

If the user supplied a question with the skill invocation, use it. Otherwise ask:

> **What would you like to know about Citeck?**

### Step 2: Search

Call `mcp__citeck__search_docs`:

```
mcp__citeck__search_docs(
  question: "<user question>",
  top_k: 5
)
```

### Step 3: Handle edge cases

- **Connection/404 error against the resolved server**, or the error message suggests no RAG is deployed on that profile — the active profile is likely a local Citeck without a RAG index. Ask the user via `AskUserQuestion` which configured profile hosts citeck-docs, then call:
  ```
  mcp__citeck__set_docs_profile(profile: "<chosen>")
  ```
  and retry the search. If the user doesn't know, explain that `docs_profile` must point to a Citeck server where the `citeck-docs` RAG repository is indexed.
- **Authentication error** — stop and instruct the user to run `/citeck:citeck-auth`.
- **Empty results (`count: 0`)** — tell the user the search returned nothing and show the `question` verbatim so they can reformulate.
- **Low scores** (all below ~0.5) — mention that matches are weak and the answer may be incomplete.

### Step 4: Synthesize an answer

Read the `content` of the returned snippets and compose a direct answer to the user's question. Rules:

- **Ground every factual claim in the snippets.** Do not invent details that aren't there.
- **Cite each claim** in parentheses right after the claim. When the snippet has a `url` field, use a markdown link: `([<file_path>](<url>))` — e.g., `([docs/general/Data_API/ECOS_Records.rst](https://citeck-ecos.readthedocs.io/ru/stable/general/Data_API/ECOS_Records.html))`. When `url` is missing, fall back to the bare path: `(<file_path>)`.
- Keep the answer concise; prefer 1-3 paragraphs or a short list. Don't dump the raw snippets.
- Answer in the same language as the question (Russian or English).
- Always show at the end: `Источник: {server}` (or `Source: {server}`) using the `server` field from the tool response so the user knows which instance was queried.

### Step 5: If the user asks a follow-up

Run the same loop again with the new question — no need to re-set `docs_profile` unless it changes.
