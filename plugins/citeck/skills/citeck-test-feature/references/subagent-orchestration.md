# Reference: Subagent Orchestration

DURABLE-ядро: как оркестратор (главный агент) делегирует прогон субагентам (`Agent` tool).
Платформо-агностично.

## Модель

Главный агент = **оркестратор**: готовит окружение, применяет config-кластеры, запускает субагентов
с предрендеренными промптами из `subagent-prompts/`, собирает результаты в отчёт. Субагенты не трогают
config и не переключают профили — это сфера оркестратора.

```
Оркестратор
 ├─ Шаг 0: smoke + safety-гейт + создать reports/<date>-<run-id>.md
 ├─ Кластер 0: pre-flight (T) лично + unit-suite
 ├─ Кластер 1 (default):
 │    ├─ Tier A read-only/API evidence — параллельно по resource locks
 │    ├─ Tier B — последовательно, один браузер
 │    └─ A+B reconciliation — под исходными case IDs
 ├─ Кластеры 2..N: по одному cluster-субагенту, между ними edit config + restart
 └─ Анализ FAIL → перепрогон → финальный вердикт
```

## Правила параллелизации

- **Tier A** — параллельно только когда cases не делят mutable fixture, conversation, config или
  внешний rate limit. `case-manifest.tsv.resource_lock` задаёт сериализацию.
- **Tier B (UI)** — строго последовательно: один Playwright-браузер на сессию.
- **Кластеры** — строго последовательны: один локальный сервис, рестарт между ними.
- Порядок не фиксирован как B-before-A: execution DAG следует dependencies. Для A+B Tier A обычно
  готовит fixture/evidence, затем Tier B завершает terminal journey.

## Делегирование: что передать субагенту

Каждый субагент-промпт (из `subagent-prompts/`, заполняется из `templates/`) содержит:
1. **Задачу** — какие ID кейсов и в каком кластере.
2. **Метод** — Tier A (HTTP+RA+LOG) / Tier B (Playwright) / cluster-mix.
3. **Контекст для прочтения** — какие `references/*` и `cases/*` прочитать один раз перед стартом.
4. **Ограничения** — профиль/стенд (`<base_url>`), safety (не мутировать вне песочницы, не менять
   config), «при FAIL не останавливаться, провести все кейсы».
5. **Формат отчёта** — `<ID>: PASS|FAIL|BLOCKED|NOT_RUN — <terminal evidence>` + дефекты.
6. **A+B handoff** — exact fixture refs, input/output, conversation/request IDs; API runner не
   выставляет PASS до UI reconciliation.

После каждого субагента оркестратор **дописывает** результаты в `reports/<date>-<run-id>.md`.

## Оркестратор-памятка (вставляется в SKILL и в README плана)

```
Сегодня: <date>. Scope: <smoke|impact|full>. Стенд: <base_url> (profile <profile>, <auth>).
Run-id: <run-id>. HEAD: <sha>. DEPLOYED_SHA: <sha>.

ШАГ 0 — Подготовка:
- Прочитать README, case-manifest, surface inventory, scenario matrix, traceability + references/*
- Safety-гейт: list_profiles + test_connection → подтвердить base_url + классификацию стенда
- validate-plan.py; blocking decision/orphan surface/scenario/case/runner → STOP для full
- Сгенерировать test-data (если есть файловые кейсы)
- Создать reports/<date>-<run-id>.md из templates/report.md

ШАГ 1 — Pre-flight (T) лично: пройти cases/pre-flight (если есть). Нерабочий инструмент — пометить.
ШАГ 2 — Unit-suite (кластер 0): из repo root полный ./mvnw clean test / ./gradlew test — зелёный.
ШАГ 3 — Кластер 1 (default):
  1. Smoke стенда (S1–S*) лично.
  2. Tier A/B выполнить по dependency/resource-lock DAG.
  3. A+B reconciliate в исходные IDs; pending channel = BLOCKED(PENDING_*), не PASS.
  4. После каждого — дописать reports/<date>-<run-id>.md.
ШАГИ 4..N — Кластеры 2..N последовательно: edit application.yml (+restart) → cluster-субагент.
  ПОСЛЕ последнего — return-to-defaults (итоговый diff равен captured baseline).
ШАГ N+1 — Анализ: FAIL → перепрогон/DEF, скриншоты, финальная сводка + вердикт.

ОГРАНИЧЕНИЯ:
- НЕ переключаться на prod/неклассифицированный стенд для мутаций (fail-closed).
- НЕ модифицировать references/* без подтверждения.
- Останавливаться перед заполнением контекста — писать промежуточные результаты в отчёт.
- Один сервис = кластеры строго последовательны.
- Full: любой required FAIL/BLOCKED/NOT_RUN/SKIP/PARTIAL → NOT_READY.
```

## Таблица «Что делать если …»

| Ситуация | Действие |
|---|---|
| Subagent-промпт отсутствует | Скопировать `templates/subagent-tier-X.md`, заполнить из `references/` |
| Найдено новое поведение | Запись в `reports/<date>-<run-id>.md` → секция «Найденные дефекты» |
| Test-data повреждены/пустые | Перегенерировать: `python3 scripts/make-*.py` |
| Config отличается после кластера | Остановиться; сверить checksum с test-patched состоянием и восстановить captured backup, не Git restore |
| Контекст субагента переполнен | Сохранить промежуточные результаты в отчёт, продолжить новой сессией |
| Unit-тест падает | Зафиксировать → перейти к следующему кластеру; финал — обязательно зелёный |
| Сессия истекла (OIDC) | `mcp__citeck__reauthenticate`, повторить операцию |
