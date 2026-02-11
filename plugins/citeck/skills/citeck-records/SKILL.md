---
name: citeck-records
description: "Query Citeck ECOS Records API on localhost for searching records, loading attributes, troubleshooting, and exploring data. Use when the user needs to interact with a local Citeck ECOS instance."
allowed-tools: Bash(curl *)
---

# Citeck ECOS Records API Client

Query the local Citeck ECOS platform via Records API for searching, troubleshooting, and data exploration.

## CRITICAL: Command Format Rules

**ALWAYS write curl commands as a single line.** Never use `\` line continuations or multi-line `-d` JSON bodies — they
break in the Bash tool. Use single quotes for URL, headers, and JSON body.

Correct:

```bash
curl -s -X POST 'http://localhost/gateway/api/records/query' -H 'Content-Type: application/json' -H 'Authorization: Basic YWRtaW46YWRtaW4=' -d '{"query":{"sourceId":"emodel/type","language":"predicate","query":{},"page":{"maxItems":10}},"attributes":{"id":"?id","name":"?disp"}}' | python3 -m json.tool
```

Wrong (WILL FAIL):

```
curl -s -X POST http://localhost/gateway/api/records/query \
  -H "Content-Type: application/json" \
  -d '{...}'
```

## CRITICAL: Data Modification Safety

**Mutate and Delete operations modify real data.** Before executing ANY `/mutate` or `/delete` request:

1. **ALWAYS ask the user for explicit confirmation** via AskUserQuestion before running the command
2. Show the user exactly what will be changed/deleted
3. Clearly label the operation as **[MUTATE]** or **[DELETE]** when presenting it

Query (`/query`) operations are read-only and safe to execute without confirmation.

## Base URL

```
http://localhost/gateway/api/records
```

## Endpoints

| Endpoint  | Method | Purpose                      | Safety                                    |
|-----------|--------|------------------------------|-------------------------------------------|
| `/query`  | POST   | Search records by predicates | Read-only, safe                           |
| `/mutate` | POST   | Create or update records     | **Modifies data — requires confirmation** |
| `/delete` | POST   | Delete records               | **Deletes data — requires confirmation**  |

## Authentication

All requests use Basic auth header (admin:admin):

```
-H 'Authorization: Basic YWRtaW46YWRtaW4='
```

## 1. Query Records (`/query`)

Search records using predicate language.

### Request Format

```bash
curl -s -X POST 'http://localhost/gateway/api/records/query' -H 'Content-Type: application/json' -H 'Authorization: Basic YWRtaW46YWRtaW4=' -d '{"query":{"sourceId":"emodel/<type-id>","language":"predicate","query":{<predicate>},"page":{"maxItems":10},"sortBy":[{"attribute":"_created","ascending":false}],"consistency":"EVENTUAL"},"attributes":{"id":"?id","disp":"?disp","name":"name?str"}}' | python3 -m json.tool
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
curl -s -X POST 'http://localhost/gateway/api/records/query' -H 'Content-Type: application/json' -H 'Authorization: Basic YWRtaW46YWRtaW4=' -d '{"query":{"sourceId":"emodel/<type-id>","language":"predicate","query":{},"page":{"maxItems":10}},"attributes":{"id":"?id","disp":"?disp"}}' | python3 -m json.tool
```

**Find records by attribute value:**

```bash
curl -s -X POST 'http://localhost/gateway/api/records/query' -H 'Content-Type: application/json' -H 'Authorization: Basic YWRtaW46YWRтaW4=' -d '{"query":{"sourceId":"emodel/<type-id>","language":"predicate","query":{"t":"eq","att":"_status","val":"active"}},"attributes":{"id":"?id","name":"name?str","status":"_status?str"}}' | python3 -m json.tool
```

**Search with multiple conditions:**

```bash
curl -s -X POST 'http://localhost/gateway/api/records/query' -H 'Content-Type: application/json' -H 'Authorization: Basic YWRtaW46YWRtaW4=' -d '{"query":{"sourceId":"emodel/<type-id>","language":"predicate","query":{"t":"and","val":[{"t":"eq","att":"_type","val":"emodel/type@my-type"},{"t":"not-empty","att":"name"},{"t":"ge","att":"_created","val":"-P30D"}]},"page":{"maxItems":20}},"attributes":{"id":"?id","name":"name?str","created":"_created?str"}}' | python3 -m json.tool
```

## 2. Load Attributes of a Specific Record

To load attributes of a known record, use query with the record ref directly:

```bash
curl -s -X POST 'http://localhost/gateway/api/records/query' -H 'Content-Type: application/json' -H 'Authorization: Basic YWRtaW46YWRtaW4=' -d '{"record":"emodel/<type-id>@<record-id>","attributes":{"id":"?id","disp":"?disp","name":"name?str","status":"_status?str","type":"_type?id","created":"_created?str","creator":"_creator?str"}}' | python3 -m json.tool
```

## 3. Load Record Full Definition

Get the YAML Full definition of an Citeck Record:

```bash
curl -s -X POST 'http://localhost/gateway/api/records/query' -H 'Content-Type: application/json' -H 'Authorization: Basic YWRtaW46YWRtaW4=' -d '{"record":"emodel/type@<type-id>","attributes":{"def":"?json|yaml()"}}' | python3 -m json.tool
```

## 4. List All Types

```bash
curl -s -X POST 'http://localhost/gateway/api/records/query' -H 'Content-Type: application/json' -H 'Authorization: Basic YWRtaW46YWRtaW4=' -d '{"query":{"sourceId":"emodel/type","language":"predicate","query":{},"page":{"maxItems":100}},"attributes":{"id":"?id","name":"?disp"}}' | python3 -m json.tool
```

## 5. [MUTATE] Create or Update Record (`/mutate`)

**Requires user confirmation before execution.**

Update existing record:

```bash
curl -s -X POST 'http://localhost/gateway/api/records/mutate' -H 'Content-Type: application/json' -H 'Authorization: Basic YWRtaW46YWRtaW4=' -d '{"record":{"id":"emodel/<type-id>@<record-id>","attributes":{"name":"New Name","_status":"approved"}}}' | python3 -m json.tool
```

Create new record (empty ID after @):

```bash
curl -s -X POST 'http://localhost/gateway/api/records/mutate' -H 'Content-Type: application/json' -H 'Authorization: Basic YWRtaW46YWRtaW4=' -d '{"record":{"id":"emodel/<type-id>@","attributes":{"name":"New Record"}}}' | python3 -m json.tool
```

## 6. [DELETE] Delete Record (`/delete`)

**Requires user confirmation before execution.**

```bash
curl -s -X POST 'http://localhost/gateway/api/records/delete' -H 'Content-Type: application/json' -H 'Authorization: Basic YWRtaW46YWRtaW4=' -d '{"records":["emodel/<type-id>@<record-id>"]}' | python3 -m json.tool
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

- Always pipe output through `python3 -m json.tool` for readable formatting
- Use `"consistency":"EVENTUAL"` for faster queries when real-time consistency is not required
- Start with small `maxItems` (5-10) to preview data before loading large datasets
- Use `?disp` attribute to get human-readable display names
- When exploring unknown record, first load the record full definition to see available attributes, via `?json`
- For troubleshooting, load `_type?id`, `_status?str`, `_created?str`, `_creator?id` as baseline attributes
