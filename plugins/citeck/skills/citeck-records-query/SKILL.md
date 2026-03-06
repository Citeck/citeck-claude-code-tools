---
name: citeck-records-query
description: "Read-only query access to Citeck ECOS Records API. Use for searching records, loading attributes, and exploring data. Does NOT include mutation capabilities."
allowed-tools: Bash(python3 */skills/citeck-records-query/scripts/query.py *), AskUserQuestion
---

# Citeck ECOS Records API — Read-Only Query

Query Citeck ECOS platform via Records API for searching, troubleshooting, and data exploration.

This skill provides READ-ONLY access. No mutation operations are available.

## Prerequisites

Run `citeck:citeck-auth` first to configure your Citeck connection (URL, credentials). If you get authentication errors, re-run `citeck:citeck-auth` to update your credentials.

## Query Records

Search records using predicate language.

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/query.py '{
  "query": {
    "sourceId": "emodel/<type-id>",
    "language": "predicate",
    "query": {},
    "page": {"maxItems": 10},
    "sortBy": [{"attribute": "_created", "ascending": false}],
    "consistency": "EVENTUAL"
  },
  "attributes": {"id": "?id", "disp": "?disp", "name": "name?str"}
}'
```

### Predicate Types

| Type         | Description             | Example                                       |
|--------------|-------------------------|-----------------------------------------------|
| `eq`         | Equals                  | `{"t":"eq","att":"status","val":"active"}`    |
| `not-eq`     | Not equals              | `{"t":"not-eq","att":"field","val":null}`     |
| `gt` / `ge`  | Greater / Greater-equal | `{"t":"ge","att":"version","val":1}`          |
| `lt` / `le`  | Less / Less-equal       | `{"t":"lt","att":"priority","val":5}`         |
| `in`         | In list                 | `{"t":"in","att":"type","val":["a","b"]}`     |
| `contains`   | Contains substring      | `{"t":"contains","att":"name","val":"test"}`  |
| `starts`     | Starts with             | `{"t":"starts","att":"title","val":"prefix"}` |
| `ends`       | Ends with               | `{"t":"ends","att":"title","val":"suffix"}`   |
| `like`       | Pattern (% = wildcard)  | `{"t":"like","att":"name","val":"%test%"}`    |
| `empty`      | Empty value             | `{"t":"empty","att":"client"}`                |
| `not-empty`  | Not empty               | `{"t":"not-empty","att":"client"}`            |
| `and` / `or` | Logical operators       | `{"t":"and","val":[...]}`                     |

### Date Predicates

| Value       | Description          |
|-------------|----------------------|
| `$NOW`      | Current datetime     |
| `$TODAY`    | Current date (00:00) |
| `-P10D`     | 10 days ago from now |
| `P1M`       | Plus 1 month         |
| `-P2Y/$NOW` | Last 2 years         |

### Common Queries

**Find all records of a type:**

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/query.py '{"query":{"sourceId":"emodel/<type-id>","language":"predicate","query":{},"page":{"maxItems":10}},"attributes":{"id":"?id","disp":"?disp"}}'
```

**Find records by attribute value:**

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/query.py '{"query":{"sourceId":"emodel/<type-id>","language":"predicate","query":{"t":"eq","att":"_status","val":"active"}},"attributes":{"id":"?id","name":"name?str","status":"_status?str"}}'
```

**Search with multiple conditions:**

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/query.py '{"query":{"sourceId":"emodel/<type-id>","language":"predicate","query":{"t":"and","val":[{"t":"eq","att":"_type","val":"emodel/type@my-type"},{"t":"not-empty","att":"name"},{"t":"ge","att":"_created","val":"-P30D"}]},"page":{"maxItems":20}},"attributes":{"id":"?id","name":"name?str","created":"_created?str"}}'
```

## Load Attributes of a Specific Record

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/query.py '{"record":"emodel/<type-id>@<record-id>","attributes":{"id":"?id","disp":"?disp","name":"name?str","status":"_status?str","type":"_type?id","created":"_created?str","creator":"_creator?str"}}'
```

## Load Record Full Definition

Get the YAML full definition of a Citeck Record:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/query.py '{"record":"emodel/type@<type-id>","attributes":{"def":"?json|yaml()"}}'
```

## List All Types

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/query.py '{"query":{"sourceId":"emodel/type","language":"predicate","query":{},"page":{"maxItems":100}},"attributes":{"id":"?id","name":"?disp"}}'
```

## Attribute Syntax Reference

### Type Modifiers

| Modifier    | Description        | Example          | Null fallback |
|-------------|--------------------|------------------|---------------|
| `?str`      | String             | `"name?str"`     | null          |
| `?id`       | Record ID          | `"manager?id"`   | null          |
| `?num`      | Number             | `"priority?num"` | null          |
| `?bool`     | Boolean            | `"active?bool"`  | null          |
| `?bool!`    | Boolean (fallback) | `"flag?bool!"`   | false         |
| `?str!`     | String (fallback)  | `"name?str!"`    | ""            |
| `?localId!` | Local ID           | `"cat?localId!"` | ""            |

### Arrays

| Syntax   | Description      |
|----------|------------------|
| `[]?str` | Array of strings |
| `[]?id`  | Array of IDs     |

### System Attributes

| Attribute       | Description   |
|-----------------|---------------|
| `?id`           | Record ID     |
| `?disp`         | Display name  |
| `_type?id`      | Record type   |
| `_status?str`   | Record status |
| `_creator?id`   | Creator       |
| `_created?str`  | Creation date |
| `_modified?str` | Modified date |
| `_parent?id`    | Parent record |

## Tips

- Use `"consistency":"EVENTUAL"` for faster queries when real-time consistency is not required
- Start with small `maxItems` (5-10) to preview data before loading large datasets
- Use `?disp` attribute to get human-readable display names
- When exploring unknown record, first load the record full definition to see available attributes, via `?json`
- For troubleshooting, load `_type?id`, `_status?str`, `_created?str`, `_creator?id` as baseline attributes
