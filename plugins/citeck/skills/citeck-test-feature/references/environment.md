# Reference: Environment & Safety

DURABLE-ядро: выбор стенда, MCP-профили, auth, **safety-политика** и smoke. Платформо-агностично —
никаких хардкодов `localhost` или конкретного namespace. Всё привязано к переменной `<base_url>`,
которая определяется на старте из выбранного стенда.

## 1. Параметры стенда (определить на старте)

Перед любой операцией зафиксировать четыре параметра и держать их как переменные прогона:

| Переменная | Что это | Откуда берётся |
|---|---|---|
| `<profile>` | MCP-профиль Citeck | `mcp__citeck__list_profiles` → выбор пользователя |
| `<base_url>` | базовый URL gateway стенда | `mcp__citeck__test_connection` (поле `url`) |
| `<auth>` | способ аутентификации | BASIC (`-u user:pass`) для локального / OIDC-cookie для удалённого |
| `<classification>` | класс стенда | стенд-политика (см. §4), НЕ угадывается по hostname |

⚠ **Все** последующие `curl`, Playwright-навигации и Records-операции бьют по `<base_url>`, а не
по `http://localhost`. Gateway-роутинг: `<base_url>/gateway/<service>/<path>` (см.
`tools-cheatsheet.md`).

## 2. Матрица профилей и auth

| Тип стенда | Пример profile | Auth | Заметки |
|---|---|---|---|
| Локальный (Launcher) | `local` | BASIC `admin:admin` (если `ENABLE_OIDC_FULL_ACCESS=false`, `BASIC_AUTH_ACCESS=admin:admin`) | Playwright-cookie не нужен — `-u admin:admin` достаточно |
| Удалённый dev/QA/staging | `dev`, `qa`, `staging` | OIDC (PKCE) — сессия через `reauthenticate` | Для curl нужен валидный токен/cookie; BASIC обычно выключен |
| Прод | `production` | OIDC | ⚠ деструктив запрещён политикой (§4) |

При session-expired на OIDC-профиле — вызвать `mcp__citeck__reauthenticate` (откроет браузер,
блокирует до логина), затем повторить операцию. НЕ гонять `citeck:citeck-auth` для смены сессии.

## 3. Smoke перед стартом (≤2 мин)

Минимальный sanity-check, прежде чем заводить кейсы. Подставить `<base_url>`/`<auth>`:

```bash
BASE=<base_url>            # напр. http://localhost  или  https://qa.example.ru
BASIC_AUTH=admin:admin     # только для BASIC local
AUTH_ARGS=(-u "$BASIC_AUTH")  # для OIDC использовать bearer/cookie array

# 1. Records API через MCP живой
mcp__citeck__test_connection            # url должен == <base_url>

# 2. Целевой сервис отвечает (health-check эндпоинт фичи; ниже — generic gateway ping)
curl -sS "${AUTH_ARGS[@]}" "$BASE/gateway/<service>/<health-or-availability-endpoint>" -w '|HTTP=%{http_code}'

# 3. Список webapps (опц. — для проверки, что нужные сервисы подняты)
#    конкретный путь зависит от платформы; см. профиль-пример examples/

# 4. Test-data (если кейсы используют файлы) — файлы непустые
ls -la <plan-dir>/test-data/ 2>/dev/null
```

Если хоть один пункт фейлится — починить до первого кейса.

Для **локального** стенда дополнительно полезно: `docker ps | grep <namespace>` (контейнеры Up),
`lsof -iTCP:<port> -sTCP:LISTEN` (если тестируемый сервис запущен вне docker, напр. через Maven).
Конкретные namespace/порт — специфика стенда, держать в профиль-примере, не здесь.

## 4. ⚠ Safety-политика (deny-by-default для деструктива)

**Центральное правило: деструктивные операции запрещены по умолчанию и разрешаются только на
стенде, явно классифицированном как non-prod с `destructive_allowed: true`.**

### Что считается деструктивом
`records_mutate` (create/update/delete), очистка тест-данных, рестарт сервиса, патч
`application.yml` / исходников, удаление workspace/folder. Всё это — **gated**.

### Read-only (разрешено после подтверждения окружения)
`records_query`, GET-эндпоинты, Playwright-навигация без мутаций, чтение логов.

### Fail-closed
При **неизвестной / неподтверждённой** классификации стенда — **СТОП**, не «спросить и
продолжить». Не угадывать non-prod по hostname: алиасы, скопированные профили, общие QA-тенанты и
прод-данные за непрод-именем обходят любую эвристику.

### ⚠ Profile-mismatch guard
MCP-роутинг (`active_profile`/`records_profile`/`ept_profile`) может указывать **не на тот** стенд,
что выбран для прогона (частый случай: active/ept = `production`, тестируем `local`). Перед любой
мутацией: сравнить `test_connection.url` с `<base_url>` выбранного стенда; при расхождении —
`set_active_profile`/`set_records_profile` на нужный и **перепроверить** `test_connection`. **Ни
одной мутации, пока active/records-профиль резолвится на стенд класса `prod`** — промах роутинга
пишет в прод даже при «намерении в local». `ept_profile` (трекер) допустимо держать на проде:
issue/комментарии — read-only.

### Liveness ДО скаффолдинга
Минимальную проверку живости стенда (`docker info`, gateway `:80`/health) делать **на safety-гейте**,
до генерации плана, а не только в pre-flight. Мёртвый стенд — дешевле абортить рано: план
скаффолдить можно (стенд не нужен), но прогон не начинать до подъёма.

### Обязательный scoping
Все мутации привязаны к выделенному тестовому `workspace`/tenant + уникальному `run-id`, чтобы
писать только в свою песочницу и не задеть чужие данные на общем стенде.

### Стенд-политика (checked-in декларация)
Скилл читает декларацию из одного из мест (в порядке приоритета):
1. `<project>/docs/plans/.test-stands.yml`
2. секция-таблица в этом файле ниже (`## Декларация стендов`)

Формат:
```yaml
# .test-stands.yml
stands:
  local:
    classification: local           # local | qa | staging | prod
    base_url: http://localhost
    destructive_allowed: true
    allowed_workspaces: ["test-*"]
  qa-main:
    classification: qa
    base_url: https://qa.example.ru
    destructive_allowed: true        # выделенный QA, сервис под контролем тестировщика
    allowed_workspaces: ["test-acceptance"]
  prod:
    classification: prod
    base_url: https://app.example.ru
    destructive_allowed: false       # read-only всегда
    allowed_workspaces: []
```

Решение по операции:
- стенд найден в политике + `destructive_allowed: true` + workspace ∈ `allowed_workspaces` →
  мутации разрешены;
- стенд найден, но `destructive_allowed: false` → только read-only;
- стенд **не найден** в политике → fail-closed (СТОП, спросить пользователя классификацию и
  попросить дописать в `.test-stands.yml`).

Кластер-кейсы с рестартом/патчем конфига допустимы **только** там, где сервис под контролем
тестировщика (по сути `local` или выделенный QA с `destructive_allowed: true`).

## Декларация стендов

> Заполняется пользователем/командой. Если есть `<project>/docs/plans/.test-stands.yml` — он
> приоритетнее. Пустая/отсутствующая декларация ⇒ всё неизвестное ⇒ fail-closed.

| profile | classification | base_url | destructive_allowed | allowed_workspaces |
|---|---|---|---|---|
| local | local | http://localhost | true | `test-*` |
| _(добавить удалённые стенды)_ | | | | |

## 5. Allowlist Claude Code (чтобы не упираться в prompt'ы)

Полезно (но не обязательно) разрешить без подтверждения в `.claude/settings.local.json`:
- `mcp__plugin_playwright_playwright__*`
- Citeck MCP read: `records_query`, `test_connection`, `search_issues`, `query_comments`,
  `list_profiles`
- `Bash(curl -* <base_url>/*)`, `Bash(python3 *async-http.py*)`, `Bash(jq *)`, `Bash(python3 -c*PIL*)`
- (локально) `Bash(docker ps:*)`, `Bash(docker logs *<namespace>*:*)`

С подтверждением **намеренно** остаются: `records_mutate`, правки `application.yml`/исходников,
`docker restart`, `git push`/`gh pr create`. Если allowlist не настроен — после первого прогона
запустить `/fewer-permission-prompts`, он соберёт точный список из транскрипта.

## 6. Создание тестового workspace (пример деструктива — только если политика разрешает)

```python
mcp__citeck__records_mutate(records=[{
  "id": "emodel/workspace@",
  "attributes": {
    "id?str": "<test-workspace-id>",
    "name?json": {"ru": "Test <feature>", "en": "Test <feature>"},
    "description?json": {"ru": "Workspace для прогона <feature>"},
    "visibility?str": "PRIVATE",          # ⚠ обязательное поле, иначе mutate падает
    "homePageLink?str": "",
    "workspaceMembers?json": [
      {"memberId": "admin", "authorities": ["emodel/person@admin"], "memberRole": "MANAGER"}
    ]
  }
}])
```

⚠ Без `visibility?str` → `Mandatory attributes are empty: visibility`.
