# Test Plan: <FEATURE> (<ISSUE>)

**Дата:** <DATE>
**Автор:** <AUTHOR>
**Ветка:** `<BRANCH>`
**Scope:** `<smoke|impact|full>`  •  **HEAD:** `<HEAD_SHA>`  •  **DEPLOYED_SHA:** `<DEPLOYED_SHA>`
**Стенд:** `<BASE_URL>` (profile `<PROFILE>`, классификация `<CLASSIFICATION>`, auth `<AUTH>`)
**Тестовый workspace:** `<TEST_WORKSPACE>`  •  **Run-id:** `<RUN_ID>`

## TL;DR

Прогон acceptance-плана для **<ISSUE>** на стенде `<BASE_URL>` через Claude Code + MCP:
Citeck MCP (`records_query`/`records_mutate`, profile `<PROFILE>`), Playwright MCP
(`mcp__plugin_playwright_playwright__browser_*`), scripted HTTP (`curl <BASE_URL>/gateway/...`),
сборка (`./mvnw test` / `./gradlew test`).

Кейсы имеют kind `contract|journey|guard`, evidence tier `A|B|A+B`, config cluster, dependencies и
resource lock. Прогон ведётся по execution DAG, а не фиксированному порядку файлов.

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
| `surface-inventory.tsv` | Все обнаруженные public/code/UI surfaces | До review покрытия |
| `scenario-matrix.tsv` | Применимость альтернативных и stateful веток по capability | Design gate |
| `case-manifest.tsv` | Канонический список ID, scopes, runner, case dependencies и locks | Design gate и запуск |
| `TRACEABILITY.md` | Capability → sources → contract/journey/guard | Review и release gate |
| `OPEN-DECISIONS.md` | Неподтверждённые продуктовые контракты | До full-прогона |
| `subagent-prompts/*.md` | Готовые промпты под tier/кластер | Запуск субагентов |
| `test-data/` | Фикстуры (PDF/DOCX/TXT/PNG) | Перед файловыми кейсами |
| `reports/<DATE>-<RUN_ID>.md` | Результат прогона | После прогона |

Из скилла читать: `references/environment.md`, `tools-cheatsheet.md`, `records-api-patterns.md`,
`playwright-tips.md`, `coverage-model.md`, `tier-cluster-model.md`, `subagent-orchestration.md`
(+ профиль-пример если релевантен).

## Tier-модель

| Tier | Кейсы | Метод | Параллелизация |
|---|---|---|---|
| **A** | API/Records/log/unit evidence | scripted HTTP + Records API + лог | По resource locks |
| **B** | UI evidence | Playwright | Последовательно |
| **A+B** | Один reconciled ID | API/RA handoff → UI terminal proof | По dependencies |

## Кластеры конфигов

| # | Конфиг | Кейсы | Что меняется |
|---|---|---|---|
| 0 | Pre-flight + unit | <T...> | — |
| 1 | Default | <большинство> | дефолт |
| <2..N> | <toggle> | <...> | `<config-key>=<value>` |

⚠ После последнего кластера — return-to-defaults: итоговый diff равен captured baseline.

## Порядок прогона

См. «Оркестратор-памятку» в `references/subagent-orchestration.md`. Кратко:
0. Discovery/review: inventory + scenario matrix + traceability + manifest + closed decisions.
1. Design gate: `validate-plan.py`, safety, HEAD/DEPLOYED_SHA, dependencies, test-data, report.
2. Pre-flight (T) лично.
3. Полный unit-suite из repo root.
4. Кластер 1: выполнить dependency/resource-lock DAG; A+B reconciliate под исходными IDs.
5..N. Кластеры конфигов последовательно; безопасно восстановить captured baseline.
N+1. Cleanup, validate report completeness, анализ FAIL и финальный verdict.

## Done criteria
- [ ] Inventory не имеет included surface без case/trace
- [ ] Для каждой included capability заполнены все строки scenario matrix
- [ ] Manifest, cases, prompts и report rows согласованы валидатором
- [ ] HEAD == DEPLOYED_SHA; blocking decisions отсутствуют
- [ ] Полный unit-suite зелёный *(только `full`)*
- [ ] Каждый `required=yes` ID имеет статус PASS *(только `full`)*
- [ ] A+B evidence reconciled под исходными IDs
- [ ] External sinks/stores/processes и forbidden effects проверены
- [ ] Cleanup выполнен; captured dirty/config baseline восстановлен

Для `full` любой `FAIL/BLOCKED/NOT_RUN/SKIP/PARTIAL` в required case означает `NOT_READY`.
Прогон `smoke`/`impact` фиксирует ограничение в `**Scope limitation:**` отчёта и не отмечает
full-only пункты Final Gate.

Только после этого ветка готова к MR.

## Что делать если
См. таблицу «Что делать если …» в `references/subagent-orchestration.md`.
