# Subagent: Tier A (API-only) — <AREA>, cluster <N>

> Заполнить `<…>` маркеры. Запускается ПАРАЛЛЕЛЬНО с другими Tier A субагентами того же кластера.

## Задача
Прогнать кейсы Tier A (API-only) набора `<AREA>` в кластере `<N>`.

**Метод:** scripted HTTP (`curl` через `<BASE_URL>/gateway/<service>/...`) + Records API
(`mcp__citeck__records_query`/`records_mutate`, profile `<PROFILE>`) + лог сервиса.
**Стенд:** `<BASE_URL>`, классификация `<CLASSIFICATION>`. **Run-id:** `<RUN_ID>`,
песочница `<TEST_WORKSPACE>`.

## Контекст (прочитать один раз перед стартом)
1. README плана — общий план + кластеры
2. Скилл `references/environment.md` — стенд, safety, smoke
3. Скилл `references/tools-cheatsheet.md` — gateway harness, async-polling
4. Скилл `references/records-api-patterns.md` — setup/verify
5. `cases/<нужный>.md` — описания кейсов по ID ниже

## Кейсы
| ID | Кейс | Из файла |
|---|---|---|
| `<ID>` | `<…>` | `cases/<…>.md` |

## Что делать с каждым кейсом
1. Прочитать раздел кейса целиком (Шаги + Acceptance).
2. Выполнить шаги (HTTP harness из cheatsheet).
3. Проверить Acceptance: HTTP-ответ (`jq`), Records API (`records_query`), лог (`grep`).
4. Записать результат: `<ID>: PASSED|FAILED|SKIPPED — <одна строка>`.

## Ограничения
- ⚠ Profile `<PROFILE>`, стенд `<BASE_URL>`. Если `test_connection` вернёт другой url — STOP,
  сообщить оркестратору.
- ⚠ curl ходит **только** на `<BASE_URL>/...`. Мутации — только в `<TEST_WORKSPACE>` и только если
  стенд `destructive_allowed: true`; иначе read-only.
- НЕ редактировать `application.yml` / не рестартовать сервис — это работа оркестратора.
- При первом FAIL не останавливаться — провести все кейсы, потом отчитаться.
- Контекст переполняется → сохранить промежуточные результаты, сообщить оркестратору.

## Финальный отчёт оркестратору
```
Subagent: tier-a-<AREA>  •  Cluster: <N>  •  Run-id: <RUN_ID>
Результат:
  <ID>: PASSED|FAILED|SKIPPED — <comment>
Найденные дефекты:
  - <description>, repro: <curl/log>
```
