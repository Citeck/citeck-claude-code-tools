---
name: citeck-test-feature
description: "Design, audit and run smoke, impact, acceptance or full regression testing for Citeck features. Inventories code/API/UI/state-machine surfaces, creates traceable contract/journey/guard cases, scaffolds a validated test-plan, and executes it with Citeck MCP, Playwright and scripted HTTP. Use for a feature, branch, tracker issue, microservice regression or coverage review."
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, AskUserQuestion, Agent, mcp__citeck__test_connection, mcp__citeck__list_profiles, mcp__citeck__set_active_profile, mcp__citeck__set_records_profile, mcp__citeck__reauthenticate, mcp__citeck__records_query, mcp__citeck__records_mutate, mcp__citeck__search_issues, mcp__citeck__query_comments, mcp__plugin_playwright_playwright__browser_navigate, mcp__plugin_playwright_playwright__browser_snapshot, mcp__plugin_playwright_playwright__browser_click, mcp__plugin_playwright_playwright__browser_type, mcp__plugin_playwright_playwright__browser_fill_form, mcp__plugin_playwright_playwright__browser_file_upload, mcp__plugin_playwright_playwright__browser_wait_for, mcp__plugin_playwright_playwright__browser_take_screenshot, mcp__plugin_playwright_playwright__browser_console_messages, mcp__plugin_playwright_playwright__browser_network_requests, mcp__plugin_playwright_playwright__browser_evaluate, mcp__plugin_playwright_playwright__browser_run_code_unsafe, mcp__plugin_playwright_playwright__browser_close
---

# Citeck Test Feature

Скилл-гид + скаффолдер приёмочного тестирования **любой** фичи платформы Citeck на выбранном стенде.
Делает две вещи: (1) служит durable-руководством КАК тестировать (см. `references/`), (2) при вызове
скаффолдит датированную папку тест-плана в целевом проекте и помогает спланировать + прогнать кейсы.

⚠ **Имена тулов:** Citeck — `mcp__citeck__*`, Playwright — `mcp__plugin_playwright_playwright__browser_*`
(полный неймспейс; короткий `mcp__playwright__*` не сматчится — это чужой плагин).

⚠ **Где пишется план:** сгенерированная папка идёт в **целевой проект**
(`<project>/docs/plans/<YYYY-MM-DD>-<issue>-test-plan/`), НЕ в репозиторий плагина.

## Durable-ядро (читать по необходимости из `${CLAUDE_SKILL_DIR}/`)

| Файл | Когда читать |
|---|---|
| `references/environment.md` | Шаг 2 — стенд, MCP-профили, **safety-политика**, smoke |
| `references/tools-cheatsheet.md` | Перед HTTP/RA-кейсами — теги, gateway harness, async-polling |
| `references/records-api-patterns.md` | Перед setup/verify через Records API |
| `references/playwright-tips.md` | Перед UI-кейсами (Tier B) |
| `references/test-case-design.md` | Шаг 5 — уровни тестирования, типы кейсов, принципы составления |
| `references/coverage-model.md` | Шаги 4–5 и 9 — inventory, terminal E2E, state matrix, full gate |
| `references/tier-cluster-model.md` | Шаги 5 и 9 — раскладка по tier'ам/кластерам, ID-конвенции, done-criteria |
| `references/subagent-orchestration.md` | Шаг 8 — оркестрация субагентов, «что делать если» |
| `examples/citeck-ai-assistant.md` | Если тестируется AI-ассистент — профиль-пример |
| `templates/*` | Шаг 6 — шаблоны плана, inventory, manifest, traceability и отчёта |
| `scripts/*.py` | Шаги 4, 6–7, 9 — discovery/scaffold/validate/HTTP helpers и генераторы фикстур |

## Flow

### 1. Сбор входных данных и режим
Через `AskUserQuestion` (если не заданы): фича/ветка, tracker-issue (опц.), целевой
проект/микросервис, **целевой стенд** (profile/URL) и `SCOPE=smoke|impact|full`. Если задан issue —
`mcp__citeck__search_issues` + `mcp__citeck__query_comments` для деталей и контекста (картинки
авто-скачиваются — прочитать их Read'ом).

`full` означает весь обязательный manifest; `impact` — dependency closure затронутых capabilities +
permanent defect guards; `smoke` — только liveness/golden journey и никогда не даёт release verdict.

### 2. ⚠ Safety-гейт (deny-by-default для деструктива)
Прочитать `${CLAUDE_SKILL_DIR}/references/environment.md`. Затем:
- `mcp__citeck__list_profiles` + `mcp__citeck__test_connection` → показать пользователю
  **фактический `base_url` + профиль**, зафиксировать `base_url` как переменную для всех
  curl/Playwright/Records-операций.
- ⚠ **Profile-mismatch guard.** Сравнить URL **выбранного** стенда с `test_connection.url` И с
  `active_profile`/`records_profile` из `list_profiles`. Если они расходятся (типовой случай: active/
  ept = `production`, а тестируем `local`) — **не продолжать на чужом профиле**: переключить
  `set_active_profile <выбранный>` (и при нужде `set_records_profile`), затем повторить
  `test_connection` и убедиться `url == <base_url выбранного стенда>`. **Жёсткое правило: ни одной
  мутации, пока active/records-профиль указывает на стенд класса `prod`** (даже если данные пишутся
  «в local» — легко промахнуться роутингом). `ept_profile` (трекер) может оставаться на проде —
  это read-only по issue/комментариям.
- ⚠ **Liveness-проба ДО скаффолдинга** (не откладывать на шаг 6). Дешёвый аборт мёртвого стенда
  раньше, чем потрачено время на генерацию плана:
  ```bash
  docker info >/dev/null 2>&1 && echo "docker UP" || echo "docker DOWN"   # если стенд докеризован
  AUTH_ARGS=(-u admin:admin) # только подтверждённый BASIC local; для OIDC — bearer/cookie array
  curl -sS -m 8 "${AUTH_ARGS[@]}" "$BASE/gateway/<service>/<health>" -w '|HTTP=%{http_code}'
  ```
  Если gateway/`:80` refused или Docker down — **СТОП**, попросить пользователя поднять стенд;
  скаффолдить план можно (стенд для этого не нужен), но прогон не начинать.
- Определить классификацию стенда по стенд-политике (`<project>/docs/plans/.test-stands.yml` или
  таблица в `environment.md` §«Декларация стендов»). **НЕ угадывать по hostname.**
- ⚠ **Bootstrap декларации.** Если `<project>/docs/plans/.test-stands.yml` отсутствует — предложить
  создать его из `${CLAUDE_SKILL_DIR}/templates/test-stands.yml` (checked-in декларация приоритетнее
  fallback-таблицы и фиксирует safety-границы в репозитории проекта), затем продолжить.
- **Решение:**
  - стенд non-prod с `destructive_allowed: true` + workspace ∈ `allowed_workspaces` → мутации разрешены;
  - `destructive_allowed: false` → только read-only (`records_query`, GET, навигация без мутаций);
  - стенд **не найден** в политике → **fail-closed: СТОП**, спросить классификацию у пользователя и
    попросить дописать в `.test-stands.yml` (не «спросить и сразу продолжить»).
- Все мутации привязывать к тестовому `workspace` + уникальному `run-id`.

### 3. Загрузка durable-контекста
Прочитать нужные `references/*` под тип фичи. Если AI-ассистент — `examples/citeck-ai-assistant.md`.

### 4. Discovery и инвентарь покрытия
До генерации кейсов исследовать не только diff/issue, но и production/frontend code, существующие
тесты, design/development plans, найденные баги, config properties и прошлые отчёты. Прочитать
`references/coverage-model.md` и заполнить `surface-inventory.tsv`: controllers/endpoints, tools,
consumers/external tasks/schedulers, state/actions, flags/limits/providers, record types/external
sinks и UI entry points. У каждой включённой поверхности должен быть case ID; исключение требует
причины и owner.

Начальный inventory для типового Citeck repo:
`python3 ${CLAUDE_SKILL_DIR}/scripts/discover-surfaces.py <project> --output <PLAN_DIR>/surface-inventory.tsv`.
Это discovery hints, не готовый оракул: вручную добавить динамические routes/state transitions и
review каждую строку.

Для `impact` сначала построить `changed files -> capabilities -> dependency closure -> cases`.
Для `full` delta не ограничивает скоуп.

### 5. Проектирование и review кейсов
Прочитать
`references/test-case-design.md` — уровни тестирования (смоук/санити/приёмка/регресс/полное), типы
кейсов (в т.ч. негатив/робастность, комплементарное покрытие «на отсутствие», темпоральное/TZ,
матрицы-эталоны прав/атрибутов) и принципы составления (источник истины = спека+код; дизайн отделён
от прогона; прогон = весь набор; расхождения спека↔код фиксировать открыто).

Каждый case получает `kind=contract|journey|guard`, `tier=A|B|A+B`, `scopes`, runner, case
dependencies и resource lock. Для каждой included capability заполнить все строки
`scenario-matrix.tsv`: happy/reject-cancel/invalid-boundary/duplicate/stale-forged/principal-acl/
concurrency/dependency-failure/retry/timeout-retention/clear-restart/cleanup. Применимая строка
обязана иметь case IDs, неприменимая — проверяемое обоснование. Заполнить
`TRACEABILITY.md`: capability должна иметь terminal journey; contract/guard не заменяют E2E.

PASS journey разрешён только после поддерживаемого entry point и durable business postcondition:
requery/reopen, реальный sink/store/process и проверка запрещённых побочных эффектов. Preview, plan,
tool call, progress или log — промежуточные assertions.

⚠ **Delta/follow-up issue.** Если фича — продолжение уже оттестированной (напр. issue ветвится от
родительской feature-ветки), **не** диффать против `merge-base develop` — он захватит весь родитель
и раздует скоуп (легко получить 20k+ строк чужого поведения). Вместо этого:
- диффать **собственный commit-range** issue (`git log <parent-feature>..<issue-branch>` или диапазон
  её фикс-коммитов) и брать только `src/main`-файлы, отсеяв шум merge-коммитов из develop;
- для `impact` можно использовать результаты прошлых прогонов как input выбора, но не как PASS
  текущего case; `full` всегда выполняет весь required manifest на текущем deployed SHA;
- центр delta-прогона — обычно один кластер (default) + узкая регрессия родителя по затронутым классам.

### 6. Скаффолдинг папки (идемпотентно)
В `<project>/docs/plans/<YYYY-MM-DD>-<issue>-test-plan/` из `templates/`: README (`plan-readme.md`),
`cases/<section>.md`, `reports/<date>-<run-id>.md`, `subagent-prompts/<...>.md`, при нужде `test-data/`,
а также `case-manifest.tsv`, `surface-inventory.tsv`, `scenario-matrix.tsv`, `TRACEABILITY.md`,
`OPEN-DECISIONS.md`.
Предпочитать:
`python3 ${CLAUDE_SKILL_DIR}/scripts/scaffold-plan.py --project-root ... --issue ... --feature ...`.
**Защита от затирания:**
- Корень плана создаётся **эксклюзивно** (create-only). Если папка уже есть — не перезаписывать
  молча: предложить `--resume` (дописать недостающее) либо новый прогон.
- **Не перезаписывать не-плейсхолдерные файлы** (отредактированные cases/README/subagent-prompts):
  затираем только файлы в шаблонном состоянии; изменённые — пропуск с предупреждением.
- Каждый отчёт — под **уникальным run-id**: `reports/<date>-<run-id>.md` (не общий `<date>.md`),
  чтобы повторный запуск/второй оператор не затёрли аудит-трейл.

Проверка идемпотентности перед записью:
```bash
PLAN_DIR="<project>/docs/plans/<YYYY-MM-DD>-<issue>-test-plan"
if [ -d "$PLAN_DIR" ]; then echo "EXISTS — resume или новый run-id, не затирать"; fi
```

### 7. Design gate и pre-flight
До live-прогона выполнить
`python3 ${CLAUDE_SKILL_DIR}/scripts/validate-plan.py <PLAN_DIR>`. Orphan surface/case, missing
runner, неполный case block, неизвестный trace ID или открытое blocking decision останавливают full.

Зафиксировать `HEAD`, dirty baseline, `DEPLOYED_SHA`, profile/base URL, provider/model/config и
dependency health. Smoke стенда (containers/порт/availability — см. `environment.md` §3).
Генерация test-data при
файловых кейсах: `python3 ${CLAUDE_SKILL_DIR}/scripts/make-text-files.py <out-dir>` и т.п.
(скрипты платформо-агностичны).

### 8. Прогон (оркестрация субагентов)
Прочитать `references/subagent-orchestration.md`. Строить execution DAG из dependencies/resource
locks: read-only Tier A параллельно; общие record/conversation/config locks последовательно; Tier B
одним браузером. `A+B` имеет один итоговый ID: API runner передаёт fixture/output Tier B и до
reconciliation не ставит PASS. После каждого субагента дописывать отчёт.

### 9. Отчёт, cleanup и гейт
Заполнить summary / дефекты / verdict. Не отмечать готовым до прохождения done-criteria
(`references/tier-cluster-model.md`). Cleanup удаляет только run-owned данные и восстанавливает
captured config baseline без destructive Git-команд.

Для `full` каждый `required=yes` ID обязан быть `PASS`; `FAIL/BLOCKED/NOT_RUN/SKIP/PARTIAL` =
`NOT_READY`. Проверить совпадение HEAD/DEPLOYED_SHA, report rows с manifest и повторно запустить
`python3 ${CLAUDE_SKILL_DIR}/scripts/validate-plan.py <PLAN_DIR> --scope full --report <REPORT>`
(`<REPORT>` — путь **относительно `<PLAN_DIR>`**, напр. `reports/<date>-<run-id>.md`).
Для `smoke` и `impact` также передавать соответствующий `--scope` и `--report`; выполнение без
отчёта не является прогоном. В отчёте smoke/impact обязательна строка `**Scope limitation:**`, а
full-only пункты Final Gate («Unit and required integration», «Every required full-run case is
PASS») остаются неотмеченными — их разрешено отмечать только на `full`.

## Оркестратор-памятка
Компактная версия — в `references/subagent-orchestration.md` («Оркестратор-памятку» вставить в
README сгенерированного плана). Там же таблица «Что делать если …».
