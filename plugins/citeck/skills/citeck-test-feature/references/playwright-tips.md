# Reference: Playwright Tips

DURABLE-ядро: auth bootstrap, стандартный набор команд, network-чек, workaround'ы. Платформо-агностично.
⚠ Имена тулов в рантайме плагина — **`mcp__plugin_playwright_playwright__browser_*`** (полный
неймспейс; короткий `mcp__playwright__*` НЕ матчится для чужого плагина). Конкретные CSS-селекторы
тестируемого UI держать в `examples/`, не здесь.

## Auth bootstrap

### Локальный стенд с BASIC auth
Chrome блокирует `http://user:pass@host/...` для fetch (SPA падает на «Server connection error»),
поэтому креды ставятся через `setExtraHTTPHeaders` **до** navigate — один раз на сессию:

```js
// browser_run_code_unsafe
async (page) => {
  // base64('admin:admin') = YWRtaW46YWRtaW4=
  await page.context().setExtraHTTPHeaders({ Authorization: 'Basic YWRtaW46YWRtaW4=' });
  return 'auth set';
}
```
Затем `browser_navigate <base_url>/v2/dashboard?ws=<workspaceId>`.

### Удалённый стенд с OIDC
BASIC-заголовок не подойдёт. Залогиниться через UI (`browser_navigate <base_url>` → форма входа
→ `browser_fill_form`/`browser_type` → submit), Playwright сохранит сессию-cookie на вкладку.
Альтернатива — если MCP-сессия уже аутентифицирована (`reauthenticate`), переиспользовать
профиль браузера.

## Стандартный набор команд для одного UI-кейса

| Шаг | Tool | Параметры |
|---|---|---|
| Auth bootstrap | `browser_run_code_unsafe` | snippet выше — один раз перед первой навигацией |
| Открыть страницу | `browser_navigate` | `<base_url>/v2/dashboard?ws=<workspaceId>` |
| Получить дерево UI | `browser_snapshot` | `depth: 3..5` (без depth — огромное дерево) |
| Кликнуть | `browser_click` | `element`+`ref` из **свежего** snapshot |
| Ввести текст | `browser_type` | `element`+`ref`+`text` (+`submit:true` для отправки) |
| Загрузить файл | `browser_file_upload` | `paths: ["/abs/path"]` |
| Дождаться состояния | `browser_wait_for` | `text:"..."` (ожидаемый контент) или `time:N` |
| Скриншот | `browser_take_screenshot` | для визуальных кейсов |
| Console errors | `browser_console_messages` | `level:"error"` после каждого кейса |
| Network 4xx/5xx | `browser_network_requests` | `static:false`, `filter:"/gateway/<service>/"` |
| Закрыть | `browser_close` | в конце прогона |

## Network-чек после каждого UI-кейса

- `browser_console_messages level=error` → не должно быть критических ошибок JS.
- `browser_network_requests filter='/gateway/<service>/'` → не должно быть 4xx/5xx на critical paths.
- Для конкретного запроса — `browser_network_request <#>` с номером из списка.

Подтверждённый flow для async-фич совпадает со scripted-HTTP harness: фронт ходит на тот же
`<base_url>/gateway/<service>/...async` (202 + requestId) и поллит статус. Фронт и curl ходят
одинаково — это удобно для cross-проверки.

## Workarounds (часто всплывают)

### Пустой/неполный snapshot после navigate
SPA рендерится асинхронно. **Всегда** ждать ключевой текст перед snapshot:
```
browser_wait_for: {text: "<якорный текст страницы>"}
browser_wait_for: {time: 3}    # fallback
```

### Ref'ы Playwright нестабильны между загрузками
`e452`, `e128` и т.д. меняются при каждом mount'е компонента. Всегда брать ref из **свежего**
snapshot — не переиспользовать ref из предыдущего шага. Если ref-клик упорно фейлится (перекрыт
или устарел) — fallback через `browser_evaluate` по CSS-селектору + тексту:
```js
() => {
  const btn = [...document.querySelectorAll('<container-selector> button')]
    .find(b => b.textContent.trim() === '<label>');
  if (!btn) return 'not found'; btn.click(); return 'clicked';
}
```
⚠ Только когда `browser_click` фейлится — JS-клики не пишутся в trace, дебажить сложнее.

### Overlay перекрывает клики (dropdown/modal/datepicker)
```js
() => {
  document.querySelectorAll('.flatpickr-calendar.open').forEach(el => el.classList.remove('open'));
  document.querySelectorAll('<dropdown-selector>').forEach(el => el.style.display = 'none');
  return 'overlays closed';
}
```
Затем повторить `browser_click`.

### `browser_file_upload` фейлится «no input found»
Виджеты часто прячут `<input type="file">` за кнопкой. Сначала кликнуть кнопку загрузки (откроется
file picker), затем сразу `browser_file_upload` — Playwright перехватит диалог. Если не сработало —
открыть native input через JS:
```js
() => {
  const input = document.querySelector('input[type="file"]');
  if (!input) return 'no input';
  input.style.cssText = 'display:block;position:fixed;z-index:9999';
  return 'visible';
}
```
⚠ Проверяй `accept`-атрибут input'а — UI может не принимать нужный тип (напр. изображения), тогда
кейс гоняется только через scripted HTTP.

### Скачать файл из ответа (для PIL/binary-verify)
1. `browser_network_requests filter='<content-endpoint>'` → найти URL превью/контента.
2. `curl -sS <auth> "<URL>" -o /tmp/out.bin` (через Bash).
3. PIL/inspect: `python3 -c "from PIL import Image; print(Image.open('/tmp/out.bin').size)"`.

## Известные шумы (игнорировать)
- `chrome-extension://invalid/` в консоли — фон от dev-расширений.
- Логи вида «Плагин недоступен» на локальном dev-плагине — некритично.
- При смене workspace через UI URL обновляется на `?ws=...$...` — использовать ту же строку для
  повторного открытия.
