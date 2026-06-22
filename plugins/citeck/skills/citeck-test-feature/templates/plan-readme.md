# Test Plan: <FEATURE> (<ISSUE>)

**Дата:** <DATE>
**Автор:** <AUTHOR>
**Ветка:** `<BRANCH>`
**Стенд:** `<BASE_URL>` (profile `<PROFILE>`, классификация `<CLASSIFICATION>`, auth `<AUTH>`)
**Тестовый workspace:** `<TEST_WORKSPACE>`  •  **Run-id:** `<RUN_ID>`

## TL;DR

Прогон acceptance-плана для **<ISSUE>** на стенде `<BASE_URL>` через Claude Code + MCP:
Citeck MCP (`records_query`/`records_mutate`, profile `<PROFILE>`), Playwright MCP
(`mcp__plugin_playwright_playwright__browser_*`), scripted HTTP (`curl <BASE_URL>/gateway/...`),
сборка (`./mvnw test` / `./gradlew test`).

Кейсы сгруппированы в **config-кластеры** (минимизация рестартов) и **2 tier'а** (A=API-only
параллельно, B=UI-only последовательно). Прогон ведёт оркестратор + субагенты.

**Текущий статус:** см. `reports/<DATE>-<RUN_ID>.md`.

## ⚠ Правило окружения и safety

- Прогон на стенде `<BASE_URL>` (profile `<PROFILE>`, классификация `<CLASSIFICATION>`).
- Деструктив (`records_mutate`, рестарт, патч config) разрешён **только** если стенд
  `destructive_allowed: true` (см. skill `references/environment.md` §4) — иначе read-only.
- Перед мутациями: `mcp__citeck__test_connection` → `url == <BASE_URL>`.
- Все мутации — в `<TEST_WORKSPACE>` + run-id `<RUN_ID>`, не задевать чужие данные.
- ⚠ Запрещён переход на prod/неклассифицированный стенд (fail-closed).

## Карта документов

Durable-методология — в скилле `citeck:citeck-test-feature` (`references/*`). Здесь — конкретика прогона.

| Файл | Что содержит | Когда читать |
|---|---|---|
| `cases/*.md` | Описания кейсов по разделам (T/S/R/F/I/C) | Перед прогоном раздела |
| `subagent-prompts/*.md` | Готовые промпты под tier/кластер | Запуск субагентов |
| `test-data/` | Фикстуры (PDF/DOCX/TXT/PNG) | Перед файловыми кейсами |
| `reports/<DATE>-<RUN_ID>.md` | Результат прогона | После прогона |

Из скилла читать: `references/environment.md`, `tools-cheatsheet.md`, `records-api-patterns.md`,
`playwright-tips.md`, `tier-cluster-model.md`, `subagent-orchestration.md` (+ профиль-пример если релевантен).

## Tier-модель

| Tier | Кейсы | Метод | Параллелизация |
|---|---|---|---|
| **A** | <большинство> | scripted curl + Records API + лог | Свободная (внутри кластера) |
| **B** | <единицы UI-smoke> | Playwright | Последовательно (один браузер) |

## Кластеры конфигов

| # | Конфиг | Кейсы | Что меняется |
|---|---|---|---|
| 0 | Pre-flight + unit | <T...> | — |
| 1 | Default | <большинство> | дефолт |
| <2..N> | <toggle> | <...> | `<config-key>=<value>` |

⚠ После последнего кластера — return-to-defaults (`git status` чист).

## Порядок прогона

См. «Оркестратор-памятку» в `references/subagent-orchestration.md`. Кратко:
0. Подготовка: safety-гейт, test-data, создать `reports/<DATE>-<RUN_ID>.md`.
1. Pre-flight (T) лично.
2. Unit-suite (кластер 0).
3. Кластер 1: smoke лично → Tier B субагент → Tier A субагенты (параллельно) → дописать отчёт.
4..N. Кластеры 2..N последовательно (edit config + restart). После последнего — return-to-defaults.
N+1. Анализ FAIL → перепрогон/DEF → финальный вердикт.

## Done criteria
- [ ] T пройдены (или нерабочие инструменты зафиксированы)
- [ ] Unit-suite зелёный
- [ ] R пройдены
- [ ] F/I пройдены или явно SKIP с обоснованием
- [ ] Provider/variant matrices — минимум один вариант каждой строки
- [ ] C-кейсы без ошибок
- [ ] Return-to-defaults выполнен (`git status` чист)

Только после этого ветка готова к MR.

## Что делать если
См. таблицу «Что делать если …» в `references/subagent-orchestration.md`.
