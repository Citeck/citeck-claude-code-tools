---
name: citeck-ask-docs
description: "Ask a question about the Citeck ECOS platform — searches citeck-docs via RAG and synthesizes an answer with citations. Use when the user asks how Citeck works, how to configure something, or about platform concepts."
---

## Client tools and paths

Use tools available in the current session by purpose; MCP names below are logical
Citeck tool names, not fixed client prefixes. Client permissions and sandbox rules apply.
Resolve `SKILL_DIR` to the absolute directory containing this loaded `SKILL.md`.
Resolve references from that directory and quote script paths, including paths with spaces.
These instructions do not create an isolated context automatically.
Claude Code: `/citeck:citeck-ask-docs`; Codex: select `$citeck:citeck-ask-docs`
from the skill picker, or request the skill by name in natural language.


# Ask Citeck Documentation

Answer questions about the Citeck ECOS platform using semantic search over the citeck-docs repository, then synthesize a concise answer grounded in the retrieved snippets.

## Prerequisites

Use the `citeck-auth` skill first so at least one profile has credentials. The docs RAG service is reached via the profile set as `docs_profile` in `~/.citeck/credentials.json` (falls back to the active profile).

Search in Russian. If no relevant snippets are returned, say that the search was empty.
If Citeck MCP is unavailable, disclose it and use local `ecos-docs` sources when available;
do not claim a RAG search occurred.

## Flow

### Step 1: Get the question

If the user supplied a question with the skill invocation, use it. Otherwise ask:

> **What would you like to know about Citeck?**

### Step 2: Search

Call `search_docs`:

When the request specifies a profile, verify its URL with `list_profiles` and pass
that explicit `profile` to the search; do not change the shared docs profile for a
one-off query. Otherwise use the configured `docs_profile`.

```
search_docs(
  question: "<user question>",
  top_k: 5
)
```

### Step 3: Handle edge cases

- **Connection/404 error against the resolved server**, or the error message suggests no RAG is deployed on that profile — the active profile is likely a local Citeck without a RAG index. Ask the user using the available user-question mechanism which configured profile hosts citeck-docs, then call:
  ```
  set_docs_profile(profile: "<chosen>")
  ```
  and retry the search. If the user doesn't know, explain that `docs_profile` must point to a Citeck server where the `citeck-docs` RAG repository is indexed.
- **Authentication error** — stop and instruct the user to use the `citeck-auth` skill
  through the current client's skill invocation mechanism.
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
