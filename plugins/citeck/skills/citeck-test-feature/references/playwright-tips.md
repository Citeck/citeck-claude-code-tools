# Reference: Playwright Tips

DURABLE-ядро: auth bootstrap, стандартный набор команд, network-чек, workaround'ы. Платформо-агностично.
Выбирать доступные браузерные инструменты по назначению и описанию сервера.
Имена `browser_*` ниже обозначают операции; фактические имена зависят от клиента.
Проверить навигацию, ввод, загрузку файлов, снимки экрана, ошибки консоли и сети.
Недоступные возможности отразить в отчёте. Селекторы конкретного UI хранить в `examples/`.

## Видимое окно браузера

По умолчанию выполнять приёмочные проверки UI в видимом окне, чтобы пользователь мог
наблюдать действия. Скрытый режим допустим, если пользователь явно выбрал его или прогон
выполняется в согласованной среде CI без графического интерфейса. Записывать режим в отчёт.

- Сохранять фокус приложения пользователя. Не вызывать `page.bringToFront()`,
  `Target.activateTarget` или команды активации приложения без просьбы показать окно.
  Не возвращать фокус принудительно: это мешает работе и скрывает его перехват браузером.
- Если нужно сохранить фокус на macOS, выбрать режим B из раздела «Режимы UI-прогона»:
  отдельный Chrome без начального окна и фоновые вкладки через CDP. Одного `open -g`
  недостаточно; обычный `context.newPage()` может активировать окно.
- Для Playwright MCP проверить режим доступного сервера. Если сервер запущен со скрытым
  браузером, использовать доступный сервер или запуск с видимым окном. Не изменять постоянную
  конфигурацию клиента и разрешения автоматически.
- Для встроенного браузера клиента использовать его видимую вкладку, если такой инструмент
  предоставлен в сессии. Наличие инструкции навыка не доказывает доступность инструмента.
- Если инструмент не поддерживает видимое окно, сообщить об ограничении до UI-прогона;
  не подменять запрошенную видимую приёмку скрытым выполнением без согласования.
- Если инструмент не позволяет сохранять фокус, сообщить об этом до запуска; выбрать
  другой доступный способ или согласовать ограничение. Для других ОС не считать
  поведение macOS доказательством отсутствия переключений фокуса.
- Сохранить правило одного браузера для автоматического прогона. Не управлять пользовательскими
  вкладками и не закрывать их без необходимости. Временное окно, оставленное пользователю
  для просмотра, явно обозначить; автоматически созданные остальные окна закрыть по завершении.

Дожидаться конкретного признака готовности UI, например видимого заголовка или элемента,
обнаруженного при просмотре страницы. Событие `networkidle` само по себе не доказывает,
что страница уже отображена; пустой ранний снимок не является доказательством сбоя UI.

## Режимы UI-прогона

Выбрать один режим до первого UI-кейса, записать его в отчёт и не смешивать режимы в одном прогоне.

| Режим | Чем управляется браузер | Фокус пользователя | Когда выбирать |
|---|---|---|---|
| **A. Браузерные инструменты клиента** | Playwright MCP или встроенный браузер: операции `browser_*` | Не гарантирован: окном управляет сервер инструментов, на macOS запуск браузера и новые вкладки могут активировать окно | Сохранение фокуса не требуется или ограничение согласовано |
| **B. Отдельный Chrome с фоновыми вкладками** | Node-скрипты Playwright через инструмент выполнения команд | Сохраняется при запуске по инструкции ниже: вкладки создаются через CDP с `background: true` | macOS, пользователь работает параллельно, нужна приёмка без смены фокуса |

- Операции `browser_*` управляют только браузером своего сервера и не видят вкладки режима B.
  Не перенастраивать MCP-сервер (например, `--cdp-endpoint`) ради подключения к Chrome режима B:
  это изменение конфигурации клиента.
- В режиме A сообщить пользователю до прогона, что окно может перехватить фокус, и записать
  наблюдаемое поведение в отчёт. Если ограничение не согласовано, перейти в режим B.
- Для режима B нужны Chrome, Node.js и пакет `playwright`, разрешаемый из каталога скрипта
  или через `NODE_PATH`. Навык не устанавливает зависимости; при их отсутствии сообщить
  об ограничении и согласовать режим A.
- Разделы «Auth bootstrap» и «Стандартный набор команд» ниже относятся к режиму A.
  «Workarounds» записаны операциями режима A; в режиме B применять те же приёмы
  через таблицу «Режим B: соответствие операций».

### Режим B: запуск Chrome на macOS

Использовать отдельный профиль для проверки и свободный локальный порт CDP. Не подключаться
к случайному существующему серверу на этом порту. Запуск GUI требует разрешения клиента,
если оно предусмотрено его политикой.

```bash
open -g -n -a "Google Chrome" --args \
  --remote-debugging-port=9333 \
  --user-data-dir="/private/tmp/citeck-pw-<run-id>" \
  --no-first-run --no-default-browser-check --no-startup-window
```

Не передавать URL при запуске: начальное окно может перехватить фокус. Дождаться доступности
`http://127.0.0.1:9333/json/version` перед первым скриптом.

### Режим B: скрипт кейса

Один скрипт на кейс или кластер: подключиться к Chrome, создать фоновую вкладку, выполнить шаги,
собрать ошибки консоли и сети, закрыть вкладку. Cookie и сессия OIDC сохраняются в профиле
`--user-data-dir` между скриптами. Скрипты класть в каталог плана, а не в репозиторий плагина.

При создании скрипта заменить `<SKILL_DIR>` абсолютным путём к каталогу навыка, а остальные
`<…>` — значениями выбранного стенда. Переменные окружения для этих значений не задаются.
Субагенту передавать абсолютный путь в промпте.

```js
// <plan>/scripts/ui-<ID>.cjs — run: node ui-<ID>.cjs
const { chromium } = require('playwright');
const { createBackgroundPage } = require('<SKILL_DIR>/examples/background-tab.cjs');

const baseUrl = '<base_url>';

(async () => {
  const browser = await chromium.connectOverCDP('http://127.0.0.1:9333');
  const { page } = await createBackgroundPage(browser);
  const problems = [];
  page.on('pageerror', error => problems.push(`pageerror: ${error.message}`));
  page.on('console', message => {
    if (message.type() === 'error') problems.push(`console: ${message.text()}`);
  });
  page.on('response', response => {
    if (response.status() >= 400 && response.url().includes('/gateway/<service>/')) {
      problems.push(`${response.status()} ${response.url()}`);
    }
  });
  try {
    // Local BASIC stand only; for OIDC fill in the login form instead.
    await page.setExtraHTTPHeaders({ Authorization: 'Basic <base64(user:password)>' });
    await page.goto(`${baseUrl}/v2/dashboard?ws=<workspaceId>`);
    await page.getByText('<якорный текст страницы>').first().waitFor();
    // Case steps go here.
    console.log(JSON.stringify({ ok: true, url: page.url(), problems }));
  } finally {
    await page.close();
    // For a CDP connection this only disconnects; Chrome keeps running for the next script.
    await browser.close();
  }
})().catch(error => {
  console.error(error);
  process.exit(1);
});
```

`examples/background-tab.cjs` создаёт вкладку через `Target.createTarget` с `background: true`
и находит соответствующий объект Page по `targetId`. Использовать возвращённый `page` для всех
действий; для следующей вкладки снова вызвать этот помощник. Не подменять его `context.newPage()`
или выбором последней вкладки по индексу.

Активной в окне Chrome может остаться старая вкладка. Это ожидаемо: Playwright читает
и изменяет новую фоновую вкладку без её выбора в окне. Проверять URL и конкретный признак
готовности на возвращённом `page`; видимость вкладки пользователю не является результатом
проверки. По просьбе показать вкладку допустимо вызвать `page.bringToFront()`.

### Режим B: соответствие операций

| Операция режима A | Режим B |
|---|---|
| `browser_navigate` | `page.goto(url)` |
| `browser_snapshot` | `page.locator('body').ariaSnapshot()` или `locator.ariaSnapshot()` для области |
| `browser_click` / `browser_type` | `page.getByRole(...).click()`, `locator.fill(text)`, `locator.press('Enter')` |
| `browser_file_upload` | `locator.setInputFiles(['/abs/path'])`; для скрытого input — `page.waitForEvent('filechooser')` перед кликом |
| `browser_wait_for` | `page.getByText('...').waitFor()`; фиксированная пауза только как fallback |
| `browser_take_screenshot` | `page.screenshot({ path })`; проверить на стенде до приёмки, фоновая вкладка может не отрисовываться |
| `browser_console_messages` | обработчики `page.on('console')` и `page.on('pageerror')` |
| `browser_network_requests` | обработчик `page.on('response')` с фильтром по статусу и `/gateway/<service>/` |
| `browser_evaluate` | `page.evaluate(() => ...)` |
| `browser_close` | `page.close()` для созданных вкладок; в конце прогона завершить Chrome с профилем `citeck-pw-<run-id>` |

Записывать способ запуска и наблюдаемое поведение фокуса в отчёт. При проверке отсутствия
перехвата отслеживать активное приложение во время всей операции, а не только после неё;
опрос с коротким интервалом не исключает переключений короче этого интервала.
Закрывать только созданные прогоном вкладки, если пользователь не попросил оставить их.

API: [Playwright connectOverCDP](https://playwright.dev/docs/api/class-browsertype#browser-type-connect-over-cdp),
[CDP Target.createTarget](https://chromedevtools.github.io/devtools-protocol/tot/Target/#method-createTarget).
CDP поддерживается только браузерами на основе Chromium и имеет ограничения по сравнению
с обычным подключением Playwright; доступность нужных операций проверять до приёмки.

## Auth bootstrap (режим A)

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

## Стандартный набор команд для одного UI-кейса (режим A)

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

В режиме B те же проверки выполняет скрипт кейса через обработчики `console`, `pageerror`
и `response`; результат выводится в его JSON-отчёт.

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
2. `curl -sS <auth> "<URL>" -o /tmp/out.bin` (через доступный инструмент выполнения команд).
3. PIL/inspect: `python3 -c "from PIL import Image; print(Image.open('/tmp/out.bin').size)"`.

## Известные шумы (игнорировать)
- `chrome-extension://invalid/` в консоли — фон от dev-расширений.
- Логи вида «Плагин недоступен» на локальном dev-плагине — некритично.
- При смене workspace через UI URL обновляется на `?ws=...$...` — использовать ту же строку для
  повторного открытия.
