# Reference: Records API Patterns

DURABLE-ядро: паттерны `mcp__citeck__records_query` / `records_mutate` для setup и verify.
Платформо-агностично. Конкретные типы/атрибуты тестируемой фичи — в `examples/` или `cases/`.

⚠ **Перед любым `records_mutate`** — `mcp__citeck__test_connection` и сверка `url == <base_url>`
выбранного стенда + проверка safety-политики (`environment.md` §4). Мутации только если стенд
классифицирован non-prod с `destructive_allowed: true`.

## 1. Listing записей (workspace и пр.)

```yaml
records_query:
  source_id: emodel/workspace
  language: predicate          # ⚠ ОБЯЗАТЕЛЬНО, иначе пустой ответ
  query: {}
  attributes:
    id: "?id"
    name: "name?json"
    visibility: "visibility?str"
```

## 2. Получить модель типа (когда нужны точные имена атрибутов)

```yaml
records_query:
  source_id: emodel/type
  query: {predicate: {t: eq, att: id, val: "<type-id>"}}
  attributes:
    model: "model?json"
```

`model.attributes[]` содержит реальные имена атрибутов. Брать оттуда, **не угадывать**.

## 3. Создать тестовую запись с текстовым content

```yaml
records_mutate:
  records:
    - id: "emodel/<type>@"               # пустой @ = создание
      attributes:
        _type: "emodel/type@<type>"
        _workspace: "<test-workspace>"   # из allowed_workspaces политики
        name: "<test-record-name>"
        _content?json:
          - storage: "internal"
            url: "data:text/plain;base64,<BASE64>"
            originalName: "sample.txt"
            mimetype: "text/plain"
            size: 1234
```

Альтернатива (практичнее): прогрузить файл через UI (`browser_file_upload`) — `_content`
создаётся автоматически.

## 4. Создать запись с image content

То же, что (3), но MIME другой:
```yaml
_content?json:
  - storage: "internal"
    url: "data:image/jpeg;base64,<BASE64>"
    originalName: "sample.jpg"
    mimetype: "image/jpeg"
    size: 12345
```

## 5. Verify: temp-ref удалён после save

```yaml
records_query:
  source_id: emodel/temp-file        # точный sourceId зависит от инструмента — см. логи
  query: {predicate: {t: eq, att: id, val: "<temp-id>"}}
  attributes:
    notExists: "_notExists?bool"
```
Acceptance: `notExists == true`. Если `false` — pending не удалился; смотри `[LOG]`.

## 6. Verify: content-версия обновлена

```yaml
records_query:
  source_id: emodel/<sourceId>
  query: {predicate: {t: eq, att: id, val: "<localId>"}}
  attributes:
    content: "_content?json"
    history: "_contentHistory[]?json"
```
Acceptance: `content[0].originalName` совпадает с ожидаемым; `content[0].url` — не data:base64
(прошёл storage); `history` (если поддерживается типом) содержит +1 запись.

## 7. Verify: named-attribute заполнен

```yaml
records_query:
  source_id: <sourceId>
  query: {predicate: {t: eq, att: id, val: "<localId>"}}
  attributes:
    attachedDoc: "<attr-name>?json"
```
Acceptance: атрибут — массив с объектом (`{originalName, url, mimetype, size}`).

## 8. Найти и удалить запись/folder (cleanup, invalidate-сценарии)

```yaml
# 1. Найти
records_query:
  source_id: emodel/<sourceId>
  query:
    predicate:
      t: and
      val:
        - {t: eq, att: name, val: "<name>"}
        - {t: eq, att: _workspace, val: "<test-workspace>"}
  attributes: {id: "?id"}

# 2. Удалить
records_mutate:
  records:
    - id: "<ref из шага 1>"
      attributes: {_delete?bool: true}
```

## 9. Cleanup тестовых артефактов после прогона

```yaml
records_query:
  source_id: <sourceId>
  query:
    predicate: {t: like, att: id, val: "%<test-workspace>%"}
  max_items: 100
# затем mutate с _delete?bool: true для каждого ref'а
```
⚠ **НЕ запускай cleanup, пока не все кейсы зелёные** — артефакты нужны для перепрогона и анализа FAIL.

## Антипаттерны

| Не делай | Делай |
|---|---|
| `_workspace: "<id>"` без проверки существования | Сначала `records_query` на `emodel/workspace` |
| `records_query` на `emodel/workspace` без `language: predicate` | `language: predicate` обязательно |
| Угадывать имена атрибутов типа | Запросить `model?json` сначала (паттерн 2) |
| `_content: "<base64>"` (string) | `_content?json: [{storage, url, originalName, mimetype, size}]` (массив объектов) |
| `possibleOutcomes?json` | `possibleOutcomes[]?json` (с `[]` если массив) |
| Удалять через UI и сразу проверять через API | После UI-удаления подождать 1–2 сек, потом `records_query` |
| `mutate` без `_workspace` для workspace-aware типов | `_workspace` всегда указывать |
| Любой profile, не сверив стенд | ⚠ `test_connection.url == <base_url>` + safety-политика перед каждой сессией мутаций |

## Когда что-то пошло не так

- `Mandatory attributes are empty: <attr>` → добавить недостающий (`visibility?str` для workspace,
  `_type` для типизированных записей).
- `Type with id ... not found` → проверь `_type` через `records_query` на `emodel/type@<id>`.
- Mutate прошёл, verify пустой → возможна задержка индексации; повторить `records_query` через
  1–2 сек или указать `_workspace` явно.
