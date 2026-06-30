---
name: citeck-test-feature
description: "Plan and run acceptance testing for a new Citeck platform feature on a chosen stand. Scaffolds a dated test-plan folder (cases/reports/subagent-prompts/test-data), uses Citeck MCP + Playwright MCP + scripted HTTP, and lays cases out across tiers and config clusters. Use when the user wants to test/QA a new Citeck feature, branch, or tracker issue end-to-end."
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, AskUserQuestion, Agent, mcp__citeck__test_connection, mcp__citeck__list_profiles, mcp__citeck__reauthenticate, mcp__citeck__records_query, mcp__citeck__records_mutate, mcp__citeck__search_issues, mcp__citeck__query_comments, mcp__plugin_playwright_playwright__browser_navigate, mcp__plugin_playwright_playwright__browser_snapshot, mcp__plugin_playwright_playwright__browser_click, mcp__plugin_playwright_playwright__browser_type, mcp__plugin_playwright_playwright__browser_fill_form, mcp__plugin_playwright_playwright__browser_file_upload, mcp__plugin_playwright_playwright__browser_wait_for, mcp__plugin_playwright_playwright__browser_take_screenshot, mcp__plugin_playwright_playwright__browser_console_messages, mcp__plugin_playwright_playwright__browser_network_requests, mcp__plugin_playwright_playwright__browser_evaluate, mcp__plugin_playwright_playwright__browser_run_code_unsafe, mcp__plugin_playwright_playwright__browser_close
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
| `references/test-case-design.md` | Шаг 4 — уровни тестирования, типы кейсов, принципы составления |
| `references/tier-cluster-model.md` | Шаг 4 — раскладка по tier'ам/кластерам, ID-конвенции, done-criteria |
| `references/subagent-orchestration.md` | Шаг 7 — оркестрация субагентов, «что делать если» |
| `examples/citeck-ai-assistant.md` | Если тестируется AI-ассистент — профиль-пример |
| `templates/*` | Шаг 5 — шаблоны генерируемой папки плана |
| `scripts/*.py` | Шаг 6 — генераторы фикстур (PDF/DOCX/TXT/PNG), требуют `python3 + PIL/reportlab/python-docx` |

## Flow

### 1. Сбор входных данных
Через `AskUserQuestion` (если не заданы): фича/ветка, tracker-issue (опц.), целевой
проект/микросервис, **целевой стенд** (profile/URL). Если задан issue —
`mcp__citeck__search_issues` + `mcp__citeck__query_comments` для деталей и контекста (картинки
авто-скачиваются — прочитать их Read'ом).

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
  curl -sS -m 8 $AUTH "$BASE/gateway/<service>/<health>" -w '|HTTP=%{http_code}'  # gateway жив?
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

### 4. Скоупинг кейсов
По диффу ветки / design-доку / описанию issue выделить новое поведение. Прочитать
`references/test-case-design.md` — уровни тестирования (смоук/санити/приёмка/регресс/полное), типы
кейсов (в т.ч. негатив/робастность, комплементарное покрытие «на отсутствие», темпоральное/TZ,
матрицы-эталоны прав/атрибутов) и принципы составления (источник истины = спека+код; дизайн отделён
от прогона; прогон = весь набор; расхождения спека↔код фиксировать открыто). Разложить по tier'ам
(A=API-параллельно, B=UI-последовательно) и кластерам (минимизация рестартов). Присвоить ID
(T/S/R/F/I/C — см. `references/tier-cluster-model.md`). До реализации зафиксировать два списка:
unit-сценарии и приёмочный чек-лист.

⚠ **Delta/follow-up issue.** Если фича — продолжение уже оттестированной (напр. issue ветвится от
родительской feature-ветки), **не** диффать против `merge-base develop` — он захватит весь родитель
и раздует скоуп (легко получить 20k+ строк чужого поведения). Вместо этого:
- диффать **собственный commit-range** issue (`git log <parent-feature>..<issue-branch>` или диапазон
  её фикс-коммитов) и брать только `src/main`-файлы, отсеяв шум merge-коммитов из develop;
- **переиспользовать** результаты прошлых прогонов (config-toggle кластеры, provider-матрицы),
  явно пометив их out-of-scope со ссылкой на прошлый отчёт, а не гонять заново;
- центр delta-прогона — обычно один кластер (default) + узкая регрессия родителя по затронутым классам.

### 5. Скаффолдинг папки (идемпотентно)
В `<project>/docs/plans/<YYYY-MM-DD>-<issue>-test-plan/` из `templates/`: README (`plan-readme.md`),
`cases/<section>.md`, `reports/<date>-<run-id>.md`, `subagent-prompts/<...>.md`, при нужде `test-data/`.
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

### 6. Pre-flight
Smoke стенда (containers/порт/availability — см. `environment.md` §3). Генерация test-data при
файловых кейсах: `python3 ${CLAUDE_SKILL_DIR}/scripts/make-text-files.py <out-dir>` и т.п.
(скрипты платформо-агностичны).

### 7. Прогон (оркестрация субагентов)
Прочитать `references/subagent-orchestration.md`. Tier A — параллельно (несколько `Agent` в одном
сообщении, внутри кластера); Tier B — последовательно (один браузер); кластеры — последовательно.
После каждого субагента **дописывать** `reports/<date>-<run-id>.md`. ⚠ Return-to-defaults после
config-кластеров.

### 8. Отчёт и гейт
Заполнить summary / дефекты / verdict. Не отмечать готовым до прохождения done-criteria
(`references/tier-cluster-model.md`): T, unit, R, F/I, matrices, C-кейсы, return-to-defaults (`git
status` чист).

## Оркестратор-памятка
Компактная версия — в `references/subagent-orchestration.md` («Оркестратор-памятку» вставить в
README сгенерированного плана). Там же таблица «Что делать если …».
