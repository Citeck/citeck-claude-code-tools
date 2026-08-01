# Reference: Tools Cheatsheet

DURABLE-ядро: палитра инструментов, теги для маркировки кейсов и **generic gateway HTTP harness**.
Платформо-агностично. Конкретные эндпоинты тестируемой фичи держать в `examples/` или в `cases/`
сгенерированного плана, не здесь.

## Палитра тегов

Помечай каждый кейс строкой `Tools:` с одним или несколькими тегами:

| Тег | Инструмент | Когда использовать |
|---|---|---|
| `[RA]` | **Records API** — `mcp__citeck__records_query` / `records_mutate` | Setup тестовых данных и verify артефактов после операции. |
| `[PW]` | **Playwright** — `mcp__plugin_playwright_playwright__browser_*` | Многошаговый UI, кнопки, file upload, превью, визуальные проверки. См. `playwright-tips.md`. |
| `[HTTP]` | **Scripted HTTP** — `curl` на `<base_url>/gateway/<service>/...` + polling | Concurrency, exotic-эндпоинты, rate-limit, прямые контракты API. |
| `[LOG]` | **Log inspection** — `tail`/`docker logs` лог сервиса | Системные сообщения, audit, режимы работы, трассировка. |
| `[FS]` | **Filesystem/Docker** — `docker ps`, правки `application.yml` + restart | Toggle-кейсы (config-кластеры). |
| `[U]` | **Unit-тесты** (`./mvnw test -Dtest=…` / `./gradlew test`) | Чистая логика guard'ов (валидация, MIME, sanitize). |
| `[BIN]` | **Binary/pixel inspection** (`python3 + PIL`) | Проверка размеров/режима/alpha изображений, бинарных артефактов. |

⚠ На macOS `identify`/`pngcheck` могут отсутствовать; `python3 + PIL` обычно есть:
```bash
python3 -c "from PIL import Image; img=Image.open('out.png'); print(img.mode, img.size, img.getextrema())"
```

## Generic gateway HTTP harness

Все запросы идут через `ecos-gateway` стенда, маршрутизация по service-discovery (Zookeeper).
Путь — `<base_url>/gateway/<service>/<path>`, где `<service>` — короткое имя приложения
(`emodel`, `eproc`, `ai`, `uiserv`, …).

```bash
BASE=<base_url>/gateway/<service>      # из выбранного стенда, НЕ хардкод localhost
BASIC_AUTH=admin:admin                 # только BASIC local
BEARER_TOKEN=                          # либо OIDC bearer для удалённого стенда
AUTH_ARGS=()
[ -n "$BASIC_AUTH" ] && AUTH_ARGS=(-u "$BASIC_AUTH")
[ -n "$BEARER_TOKEN" ] && AUTH_ARGS=(-H "Authorization: Bearer $BEARER_TOKEN")
```

⚠ Auth зависит от стенда (см. `environment.md` §2). BASIC `-u admin:admin` — только когда стенд
явно с `ENABLE_OIDC_FULL_ACCESS=false`. Для удалённых стендов — токен/cookie из аутентифицированной
сессии. Не хранить `-u user:pass` строкой и не рассчитывать на shell word splitting.

### Async-polling паттерн (типовой для платформенных async-API)

Многие платформенные эндпоинты возвращают `requestId` и обрабатываются асинхронно:

Использовать fail-closed helper вместо копирования циклов:

```bash
export BASIC_AUTH=admin:admin  # или BEARER_TOKEN; не оба
python3 "${CLAUDE_SKILL_DIR}/scripts/async-http.py" submit \
  --url "$BASE/<async-endpoint>" --data-file request.json
python3 "${CLAUDE_SKILL_DIR}/scripts/async-http.py" poll \
  --url "$BASE/<status-endpoint>/<requestId>" --attempts 60 --interval 2
python3 "${CLAUDE_SKILL_DIR}/scripts/async-http.py" cancel \
  --url "$BASE/<status-endpoint>/<requestId>"
```

Helper требует exact `202` на submit, продолжает только на `202` polling, завершает только на `200`
с JSON, а timeout/unexpected status/invalid JSON возвращает non-zero. Если конкретный endpoint имеет
другой документированный контракт, зафиксировать его в case и передать explicit expected status.

Типовой контракт: `POST` → `202 {requestId}`; `GET .../{requestId}` → `202 {status:processing}`
пока обрабатывается, `200 {result}` при готовности, `500 {error}` при ошибке; `DELETE .../{requestId}`
— отмена. Конкретные пути и payload — в профиле фичи (`examples/` или `cases/`).

### File upload контракт (через ECOS emodel webapp)

Многие фичи не имеют собственного multipart-эндпоинта — файл грузится в ECOS, ref передаётся дальше:

```bash
curl -sS "${AUTH_ARGS[@]}" -X POST "<base_url>/gateway/emodel/api/ecos/webapp/content" \
  -F "file=@<path-to-file>"
# → {"entityRef":"emodel/temp-file@<uuid>"}
```
- Field name: **`file`** (один файл за запрос), Content-Type `multipart/form-data`.
- Альтернатива для маленьких файлов — `records_mutate` на `emodel/temp-file@` с base64
  (см. `records-api-patterns.md`).

### Concurrency

Два `curl` параллельно с одним идентификатором сессии/conversation → проверка race-условий
(кто-то один побеждает, проигравший temp-ресурс удаляется).

## Когда что-то пошло не так

- Endpoint 404 через gateway → проверь, что сервис зарегистрирован (`<service>` верный) и поднят.
- `401/403` → auth: BASIC выключен на этом стенде, нужен OIDC-cookie; или сессия истекла →
  `reauthenticate`.
- Async-запрос «висит» → проверь polling-эндпоинт и таймаут сервиса (обычно минуты), смотри `[LOG]`.
