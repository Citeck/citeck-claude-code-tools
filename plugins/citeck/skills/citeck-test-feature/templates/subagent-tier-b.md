# Subagent: Tier B (UI-only) — <AREA>, cluster <N>

> Заполнить `<…>` маркеры. Запускается ПОСЛЕДОВАТЕЛЬНО — один Playwright-браузер на сессию.

## Задача
Прогнать Tier B и UI-части A+B ID набора `<AREA>` через Playwright. Reconcile evidence под
исходным ID; не создавать отдельный PASS для UI-дубля.

**Окно браузера:** видимое по умолчанию; соблюдать правила
`<SKILL_DIR>/references/playwright-tips.md`. Сохранять фокус пользователя; выводить окно
вперёд только по его просьбе. Скрытый режим, его согласование и ограничения сохранения
фокуса указать в отчёте.

**Режим UI-прогона:** `<A|B>` — выбран оркестратором по разделу «Режимы UI-прогона»,
не смешивать в одном прогоне.
- **A** — браузерные инструменты клиента (`browser_navigate`/`snapshot`/`click`/`type`/
  `file_upload`/`console_messages`/`network_requests`/…). Фокус не гарантирован.
- **B** — отдельный Chrome на CDP `<CDP_URL>` с фоновыми вкладками; каждый кейс — Node-скрипт
  по шаблону «Режим B: скрипт кейса» в `<PLAN_DIR>/scripts/`. Операции `browser_*` к этому
  Chrome не применять; использовать таблицу «Режим B: соответствие операций».

**Стенд:** `<BASE_URL>`. **Run-id:** `<RUN_ID>`, песочница `<TEST_WORKSPACE>`.
`<SKILL_DIR>` — абсолютный путь к каталогу навыка `citeck-test-feature`; субагент не вычисляет его сам.

## Контекст (прочитать один раз)
1. README плана
2. `<SKILL_DIR>/references/environment.md` — стенд, workspace, safety
3. `<SKILL_DIR>/references/playwright-tips.md` — режимы, auth bootstrap, network-чек, workaround'ы
4. `<SKILL_DIR>/examples/<профиль>.md` — селекторы конкретного UI (если есть)
5. `cases/<нужный>.md` — описания кейсов

## Auth + setup (до первой навигации)
Режим A: для локального BASIC-стенда — `browser_run_code_unsafe` с `setExtraHTTPHeaders`
(см. playwright-tips). Для OIDC — логин через UI. Затем
`browser_navigate <BASE_URL>/v2/dashboard?ws=<TEST_WORKSPACE>`.
Режим B: `page.setExtraHTTPHeaders` в скрипте для BASIC; для OIDC — форма входа в первом скрипте,
сессия сохраняется в профиле Chrome прогона.

## Кейсы
| ID | Кейс | Из файла |
|---|---|---|
| `<ID>` | `<…>` | `cases/<…>.md` |

## Что делать с каждым кейсом
1. **Между кейсами** — clear-context виджета (НЕ close+reopen, НЕ reload), если применимо.
2. **Сначала выбрать агента/контекст, потом прикреплять файл** (switch сбрасывает upload).
3. Выполнить шаги из `cases/<…>.md`.
4. После каждого: нет критических ошибок консоли и 4xx/5xx на `/gateway/<service>/`
   critical paths. Режим A — `browser_console_messages level=error` и
   `browser_network_requests filter='/gateway/<service>/'`; режим B — JSON-отчёт скрипта.
5. Визуальные кейсы — скриншот в `reports/screenshots/` (`browser_take_screenshot` или
   `page.screenshot`).
6. Для journey проверить durable terminal oracle: save/reload/reopen, process/sink и forbidden
   effects, а не только rendering/action card.
7. Записать: `<ID>: PASS|FAIL|BLOCKED|NOT_RUN — <terminal evidence / screenshot>`.

## Ограничения
- ⚠ Один браузер — не открывать parallel tabs без необходимости; в режиме B закрывать созданные вкладки.
- ⚠ НЕ редактировать `application.yml` — работа оркестратора.
- ⚠ Стенд `<BASE_URL>`; мутации только в `<TEST_WORKSPACE>` при `destructive_allowed: true`.

## Финальный отчёт оркестратору
```
Subagent: tier-b-<AREA>  •  Cluster: <N>  •  Run-id: <RUN_ID>
Результат:
  <ID>: PASS|FAIL|BLOCKED|NOT_RUN — <terminal evidence; forbidden effects; cleanup>
Console/network проблемы:
  <ID>: <list>
Скриншоты: reports/screenshots/<file>
```
