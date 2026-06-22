# Subagent: Tier B (UI-only) — <AREA>, cluster <N>

> Заполнить `<…>` маркеры. Запускается ПОСЛЕДОВАТЕЛЬНО — один Playwright-браузер на сессию.

## Задача
Прогнать кейсы Tier B (UI) набора `<AREA>` в кластере `<N>` через Playwright.

**Метод:** Playwright MCP (`mcp__plugin_playwright_playwright__browser_navigate`/`snapshot`/`click`/
`type`/`file_upload`/`console_messages`/`network_requests`/…).
**Стенд:** `<BASE_URL>`. **Run-id:** `<RUN_ID>`, песочница `<TEST_WORKSPACE>`.

## Контекст (прочитать один раз)
1. README плана
2. Скилл `references/environment.md` — стенд, workspace, safety
3. Скилл `references/playwright-tips.md` — auth bootstrap, network-чек, workaround'ы
4. `examples/<профиль>.md` — селекторы конкретного UI (если есть)
5. `cases/<нужный>.md` — описания кейсов

## Auth + setup (до первого `browser_navigate`)
Для локального BASIC-стенда — `browser_run_code_unsafe` с `setExtraHTTPHeaders` (см. playwright-tips).
Для OIDC — логин через UI. Затем `browser_navigate <BASE_URL>/v2/dashboard?ws=<TEST_WORKSPACE>`.

## Кейсы
| ID | Кейс | Из файла |
|---|---|---|
| `<ID>` | `<…>` | `cases/<…>.md` |

## Что делать с каждым кейсом
1. **Между кейсами** — clear-context виджета (НЕ close+reopen, НЕ reload), если применимо.
2. **Сначала выбрать агента/контекст, потом прикреплять файл** (switch сбрасывает upload).
3. Выполнить шаги из `cases/<…>.md`.
4. После каждого: `browser_console_messages level=error` (нет критических),
   `browser_network_requests filter='/gateway/<service>/'` (нет 4xx/5xx на critical paths).
5. Визуальные кейсы — `browser_take_screenshot` в `reports/screenshots/`.
6. Записать: `<ID>: PASSED|FAILED|SKIPPED — <одна строка / путь к скриншоту>`.

## Ограничения
- ⚠ Один браузер — не открывать parallel tabs без необходимости.
- ⚠ НЕ редактировать `application.yml` — работа оркестратора.
- ⚠ Стенд `<BASE_URL>`; мутации только в `<TEST_WORKSPACE>` при `destructive_allowed: true`.

## Финальный отчёт оркестратору
```
Subagent: tier-b-<AREA>  •  Cluster: <N>  •  Run-id: <RUN_ID>
Результат:
  <ID>: PASSED|FAILED|SKIPPED — <comment>
Console/network проблемы:
  <ID>: <list>
Скриншоты: reports/screenshots/<file>
```
