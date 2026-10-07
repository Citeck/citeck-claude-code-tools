---
name: citeck-test-feature
description: "Design, audit and run smoke, impact or full acceptance/regression testing of Citeck features, branches and tracker issues. Inventory API/UI/state surfaces, create traceable plans and execute cases with Citeck MCP, browser tools and HTTP."
allowed-tools: >-
  Read,
  Write,
  Edit,
  Glob,
  Grep,
  AskUserQuestion,
  Agent,
  Bash(python3 "${CLAUDE_SKILL_DIR}/scripts/*),
  Bash(git status*),
  Bash(git rev-parse *),
  Bash(git log *),
  Bash(git diff *),
  Bash(docker ps*),
  Bash(docker logs *),
  mcp__plugin_citeck_citeck__test_connection,
  mcp__plugin_citeck_citeck__list_profiles,
  mcp__plugin_citeck_citeck__set_active_profile,
  mcp__plugin_citeck_citeck__set_records_profile,
  mcp__plugin_citeck_citeck__reauthenticate,
  mcp__plugin_citeck_citeck__records_query,
  mcp__plugin_citeck_citeck__search_issues,
  mcp__plugin_citeck_citeck__query_comments,
  mcp__plugin_citeck_citeck__download_attachment,
  mcp__plugin_playwright_playwright,
  mcp__playwright
---

## Client compatibility

Shared by Claude Code and Codex.
- Skill directory: `${CLAUDE_SKILL_DIR}`. Claude Code substitutes it; if it appears unexpanded,
  use the absolute directory containing this `SKILL.md`.
- Quote script paths and run each script command as shown, one per call, without loops or
  shell variables: Claude Code pre-approves exactly these forms.
- In `references/` and `templates/`, `${SKILL_DIR}` and `<SKILL_DIR>` mean this same directory
  (not substituted there; use the value above).
- MCP tools are named without the client prefix.
- User-question mechanism: `AskUserQuestion` in Claude Code; elsewhere the client's question
  tool, or ask in chat and wait for the answer.

# Citeck Test Feature

Навык описывает методику приёмочного тестирования платформы Citeck и создаёт каталог
плана в целевом проекте. Справочники в `references/` помогают спланировать и выполнить проверки.

Выбирать Citeck MCP и браузерные инструменты по описанию и возможностям доступного сервера.
Перед проверкой UI убедиться, что доступны навигация, ввод, загрузка файлов, снимки экрана,
ошибки консоли и неудачные сетевые запросы. Недоступные операции указать в отчёте;
не объявлять связанные проверки выполненными.
UI-приёмка — в видимом окне без смены фокуса; см.
`references/playwright-tips.md`, разделы «Видимое окно браузера» и «Режимы UI-прогона».

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
Запросить у пользователя недостающие данные: фича/ветка, tracker-issue (опц.), целевой
проект/микросервис, **целевой стенд** (profile/URL) и `SCOPE=smoke|impact|full`. Если задан issue —
`search_issues` + `query_comments` для деталей и контекста (картинки
авто-скачиваются — открыть их доступным инструментом просмотра изображений).

`full` означает весь обязательный manifest; `impact` — dependency closure затронутых capabilities +
permanent defect guards; `smoke` — только liveness/golden journey и никогда не даёт release verdict.

### 2. Выбор стенда и разрешённых операций

Прочитать `${CLAUDE_SKILL_DIR}/references/environment.md` и применимые инструкции проекта об авторизации.
Через `list_profiles` выбрать профиль и сверить его адрес с `test_connection.url`.
Показать пользователю фактический профиль и адрес, сохранить их для всех HTTP/UI/Records операций.
Предпочитать явный `profile` для каждого вызова; при необходимости смены через `set_active_profile`/`set_records_profile`
действовать последовательно и повторить проверку адреса. Не выполнять мутации, пока
active/records-профиль указывает на production. Профиль трекера может оставаться production
для чтения задач и комментариев.

До выполнения случаев проверить доступность gateway и Docker, если стенд использует Docker.
При недоступности стенда остановить выполнение и сообщить пользователю; подготовка плана допустима.
Авторизацию брать из инструкций проекта, не угадывать пароль или способ входа.

Применить декларацию `<project>/docs/plans/.test-stands.yml`; если её нет, предложить создать
из `${CLAUDE_SKILL_DIR}/templates/test-stands.yml`. Декларация имеет приоритет над справочником.
Не определять класс стенда по hostname. Если стенд не указан в политике, остановить выполнение
до согласования и записи классификации. Мутации допустимы только на non-prod с
`destructive_allowed: true`, в `allowed_workspaces`, с уникальным `run-id`.
При `destructive_allowed: false` допустимо только чтение. Все остальные правила защиты
и проверки среды описаны в `references/environment.md`.

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
`python3 "${CLAUDE_SKILL_DIR}/scripts/discover-surfaces.py" <project> --output <PLAN_DIR>/surface-inventory.tsv`.
Это discovery hints, не готовый оракул: вручную добавить динамические routes/state transitions и
review каждую строку.

Для `impact` сначала построить `changed files -> capabilities -> dependency closure -> cases`.
Для `full` delta не ограничивает скоуп.

### 5. Проектирование и review кейсов
Прочитать `references/test-case-design.md` и применить описанные уровни тестирования,
виды случаев и принципы проверки. Явно записать расхождения требований и кода.

Каждый case получает `kind=contract|journey|guard`, `tier=A|B|A+B`, `scopes`, runner, case
dependencies и resource lock. Для каждой included capability заполнить все строки
`scenario-matrix.tsv`: happy/reject-cancel/invalid-boundary/duplicate/stale-forged/principal-acl/
concurrency/dependency-failure/retry/timeout-retention/clear-restart/cleanup. Применимая строка
обязана иметь case IDs, неприменимая — проверяемое обоснование. Заполнить
`TRACEABILITY.md`: capability должна иметь terminal journey; contract/guard не заменяют E2E.

PASS journey разрешён только после поддерживаемого entry point и durable business postcondition:
requery/reopen, реальный sink/store/process и проверка запрещённых побочных эффектов. Preview, plan,
tool call, progress или log — промежуточные assertions.

Для задачи, продолжающей ранее проверенную ветку, применить правила сравнения и повторной
проверки из `references/coverage-model.md`, раздел «Follow-up branches». Результаты прошлого
прогона помогают выбрать случаи для `impact`, но не заменяют текущий результат.

### 6. Скаффолдинг папки (идемпотентно)
В `<project>/docs/plans/<YYYY-MM-DD>-<issue>-test-plan/` из `templates/`: README (`plan-readme.md`),
`cases/<section>.md`, `reports/<date>-<run-id>.md`, `subagent-prompts/<...>.md`, при нужде `test-data/`,
а также `case-manifest.tsv`, `surface-inventory.tsv`, `scenario-matrix.tsv`, `TRACEABILITY.md`,
`OPEN-DECISIONS.md`.
Предпочитать:
`python3 "${CLAUDE_SKILL_DIR}/scripts/scaffold-plan.py" --project-root ... --issue ... --feature ...`.
**Защита от затирания:**
- Корень плана создаётся **эксклюзивно** (create-only). Если папка уже есть — не перезаписывать
  молча: предложить `--resume` (дописать недостающее) либо новый прогон.
- **Не перезаписывать не-плейсхолдерные файлы** (отредактированные cases/README/subagent-prompts):
  затираем только файлы в шаблонном состоянии; изменённые — пропуск с предупреждением.
- Каждый отчёт — под **уникальным run-id**: `reports/<date>-<run-id>.md` (не общий `<date>.md`),
  чтобы повторный запуск/второй оператор не затёрли аудит-трейл.

Перед записью проверить существование каталога плана и выбрать продолжение или новый `run-id`.

### 7. Design gate и pre-flight
До live-прогона выполнить
`python3 "${CLAUDE_SKILL_DIR}/scripts/validate-plan.py" <PLAN_DIR>`. Orphan surface/case, missing
runner, неполный case block, неизвестный trace ID или открытое blocking decision останавливают full.

Зафиксировать `HEAD`, dirty baseline, `DEPLOYED_SHA`, profile/base URL, provider/model/config и
dependency health. Smoke стенда (containers/порт/availability — см. `environment.md` §3).
Генерация test-data при
файловых кейсах: `python3 "${CLAUDE_SKILL_DIR}/scripts/make-text-files.py" <out-dir>` и т.п.
(скрипты платформо-агностичны).

### 8. Выполнение проверок
Прочитать `references/subagent-orchestration.md`. Делегировать только при наличии инструментов
и разрешении в текущей сессии. Иначе главный агент выполняет те же задания последовательно,
сохраняя все случаи, блокировки и критерии результата. Строить execution DAG из dependencies/resource
locks: read-only Tier A параллельно; общие record/conversation/config locks последовательно; Tier B
одним браузером в одном режиме UI-прогона (A или B из playwright-tips, «Режимы UI-прогона»). `A+B` имеет один итоговый ID: API runner передаёт fixture/output Tier B и до
reconciliation не ставит PASS. После каждого субагента дописывать отчёт.

### 9. Отчёт, cleanup и гейт
Заполнить summary / дефекты / verdict. Не отмечать готовым до прохождения done-criteria
(`references/tier-cluster-model.md`). Cleanup удаляет только run-owned данные и восстанавливает
captured config baseline без destructive Git-команд.

Для `full` каждый `required=yes` ID обязан быть `PASS`; `FAIL/BLOCKED/NOT_RUN/SKIP/PARTIAL` =
`NOT_READY`. Проверить совпадение HEAD/DEPLOYED_SHA, report rows с manifest и повторно запустить
`python3 "${CLAUDE_SKILL_DIR}/scripts/validate-plan.py" <PLAN_DIR> --scope full --report <REPORT>`
(`<REPORT>` — путь **относительно `<PLAN_DIR>`**, напр. `reports/<date>-<run-id>.md`).
Для `smoke` и `impact` также передавать соответствующий `--scope` и `--report`; выполнение без
отчёта не является прогоном. В отчёте smoke/impact обязательна строка `**Scope limitation:**`, а
full-only пункты Final Gate («Unit and required integration», «Every required full-run case is
PASS») остаются неотмеченными — их разрешено отмечать только на `full`.

## Оркестратор-памятка
Компактная версия — в `references/subagent-orchestration.md` («Оркестратор-памятку» вставить в
README сгенерированного плана). Там же таблица «Что делать если …».
