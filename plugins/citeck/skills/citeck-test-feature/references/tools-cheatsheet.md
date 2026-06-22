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
AUTH='-u admin:admin'                  # BASIC для local; для удалённого — OIDC-cookie/токен
```

⚠ Auth зависит от стенда (см. `environment.md` §2). BASIC `-u admin:admin` — только когда стенд
явно с `ENABLE_OIDC_FULL_ACCESS=false`. Для удалённых стендов — токен/cookie из аутентифицированной
сессии.

### Async-polling паттерн (типовой для платформенных async-API)

Многие платформенные эндпоинты возвращают `requestId` и обрабатываются асинхронно:

```bash
# 1. Отправить запрос → 202 + {requestId}
RESP=$(curl -sS $AUTH -X POST "$BASE/<async-endpoint>" \
  -H 'Content-Type: application/json' -d '<payload>')
REQ_ID=$(echo "$RESP" | jq -r .requestId)

# 2. Поллинг до готовности
for i in $(seq 1 60); do
  POLL=$(curl -sS $AUTH "$BASE/<status-endpoint>/$REQ_ID" -w '|HTTP=%{http_code}')
  CODE=${POLL##*|HTTP=}; BODY=${POLL%|HTTP=*}
  if [ "$CODE" = "200" ] && echo "$BODY" | jq -e .result >/dev/null 2>&1; then
    echo "$BODY" | jq .result; break
  fi
  if [ "$CODE" = "500" ]; then echo "ERROR: $BODY"; break; fi
  sleep 2
done
```

Типовой контракт: `POST` → `202 {requestId}`; `GET .../{requestId}` → `202 {status:processing}`
пока обрабатывается, `200 {result}` при готовности, `500 {error}` при ошибке; `DELETE .../{requestId}`
— отмена. Конкретные пути и payload — в профиле фичи (`examples/` или `cases/`).

### File upload контракт (через ECOS emodel webapp)

Многие фичи не имеют собственного multipart-эндпоинта — файл грузится в ECOS, ref передаётся дальше:

```bash
curl -sS $AUTH -X POST "<base_url>/gateway/emodel/api/ecos/webapp/content" \
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
