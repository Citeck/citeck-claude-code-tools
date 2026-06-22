# План: универсальный скилл тестирования фич платформы Citeck

## Context

Каждый раз при тестировании новой функциональности платформы Citeck приходится заново
изобретать подход: какие инструменты использовать (Citeck MCP, Playwright MCP, scripted
HTTP через gateway), как безопасно работать со стендом, какие паттерны Records API
применять, как раскладывать кейсы по tier'ам и кластерам конфигов, как оформлять отчёт.

Вся эта durable-методология уже выкристаллизовалась в плане **COREDEV-159**
(`citeck-ai/docs/plans/2026-05-07-coredev-159/`): runbook, шаблоны субагентов, шаблон
отчёта, tier/cluster-модель, паттерны Records API и Playwright. Но она «зашита» в один
датированный план и не переиспользуется.

**Цель:** извлечь переиспользуемое ядро в **скилл плагина `citeck`**, который:
1. служит durable-руководством (КАК тестировать любую фичу платформы),
2. при вызове **скаффолдит** датированную папку тест-плана в целевом проекте и помогает
   спланировать + прогнать кейсы.

**Решения (согласованы с пользователем):**
- **Охват:** вся платформа Citeck. Durable-ядро (Records API, Playwright auth, gateway
  HTTP harness, tier/cluster-модель, отчётность, оркестрация субагентов) + **citeck-ai как
  один из примеров-профилей**.
- **Стенд/профиль — параметризуемый, не захардкожен.** Тестировщики гоняют не только на
  `local`, но и на удалённых стендах (dev/staging/QA). Скилл на старте **узнаёт и явно
  подтверждает** целевой стенд (base URL + MCP-профиль + способ auth), затем привязывает все
  curl/Playwright/Records-операции к выбранному `base_url` (а не к захардкоженному
  `http://localhost`). Safety-гейт = **подтверждение окружения и блокировка случайного
  прода**, а не «только localhost».
- **Поведение:** гид + скаффолдинг плана (читает runbook → генерит папку плана → помогает
  прогнать).
- **Расположение (уточнено пользователем):** скилл плагина в репозитории
  **`citeck-claude-code-tools`** →
  `plugins/citeck/skills/citeck-test-feature/`. Это тот же плагин `citeck` (v3.8.0),
  откуда грузятся `citeck:citeck-ask-docs`, `citeck:citeck-auth` и т.д. Инвокация:
  `/citeck:citeck-test-feature`. Версионируется и раздаётся через marketplace — лучше, чем
  локальный `~/.claude/skills`.
- **Язык:** контент runbook/шаблонов — русский (как существующие планы). Frontmatter
  `description` — английский (для авто-триггера и единообразия со старшими скиллами).

**Ревизия (2026-06-22, по итогам Codex adversarial-review):** в план внесены три усиления —
(1) Playwright MCP добавлен в `allowed-tools` (без него Tier B/safety-verification падали бы на
инвокации); (2) защита от прода переведена с эвристики «URL выглядит как prod» на
**deny-by-default + явную стенд-политику + fail-closed + workspace/run-id scoping**;
(3) скаффолдинг сделан **идемпотентным** (эксклюзивный create, без затирания правок, отчёты
под уникальным run-id).

## Соглашения плагина (подтверждены чтением репозитория)

- Скиллы: `plugins/citeck/skills/<name>/SKILL.md`. Манифест
  `plugins/citeck/.claude-plugin/plugin.json` (`"skills": "./skills/"`) подхватывает папку
  автоматически — отдельной регистрации скилла не нужно.
- Frontmatter: `name`, `description` (строка в кавычках, EN), `allowed-tools`
  (через запятую), опц. `context: fork`.
- ⚠ **Именование MCP-тулов внутри плагина — `mcp__citeck__<tool>`** (НЕ
  `mcp__plugin_citeck_citeck__...`). Проверено в `citeck-changes-to-task/SKILL.md`.
- Supporting-файлы рядом со SKILL.md, ссылка через `${CLAUDE_SKILL_DIR}/...`
  (напр. `${CLAUDE_SKILL_DIR}/../_shared/...` для кросс-скилльных). Inline-bash в теле
  через `!` (напр. `` !`git branch --show-current` ``).
- Скилл должен быть самодостаточным: durable-знание **копируем/обобщаем** из плана
  COREDEV-159 внутрь скилла, а не ссылаемся на чужой репозиторий.

## Целевая структура скилла

```
plugins/citeck/skills/citeck-test-feature/
├── SKILL.md                          # методология + flow скаффолдинга/прогона (тело RU, frontmatter EN)
├── references/                       # DURABLE-ядро (платформо-агностичное)
│   ├── environment.md                # выбор стенда, профили MCP, ⚠ safety-правила, smoke-проверки
│   ├── tools-cheatsheet.md           # теги [RA]/[PW]/[HTTP]/[LOG]/[FS]/[U]/[BIN], gateway HTTP harness, async-polling
│   ├── records-api-patterns.md       # сниппеты records_query/mutate + антипаттерны
│   ├── playwright-tips.md            # auth bootstrap, network-flow, console/network-чек, workaround'ы
│   ├── tier-cluster-model.md         # tier A/B, кластеры конфигов, ID-конвенции кейсов, done-criteria
│   └── subagent-orchestration.md     # как оркестратор делегирует субагентам
├── examples/
│   └── citeck-ai-assistant.md        # ПРОФИЛЬ-ПРИМЕР: chat endpoints, селекторы чата, агенты, file/image upload contract
├── templates/                        # шаблоны для генерируемой папки плана (плейсхолдеры <feature>/<date>/<cluster>)
│   ├── plan-readme.md
│   ├── case.md
│   ├── report.md
│   ├── subagent-tier-a.md
│   ├── subagent-tier-b.md
│   └── subagent-cluster.md
└── scripts/                          # опционально: переиспользуемые генераторы фикстур
    ├── make-text-files.py            # PDF/DOCX/TXT (reportlab/python-docx)
    ├── make-images.py                # PNG (PIL): transparent/landscape/portrait
    └── make-large-pdf.py             # большой PDF (limit-тесты)
```

Источники для извлечения (из `citeck-ai/docs/plans/2026-05-07-coredev-159/`):
`runbook/*`, `subagent-prompts/_template-*.md`, `reports/_template.md`,
`test-data/generators/*`.

**Важно:** сгенерированная папка тест-плана пишется в **целевой проект**
(`<project>/docs/plans/<YYYY-MM-DD>-<issue>-test-plan/`), а НЕ в репозиторий плагина.

## DURABLE-ядро (references/) vs ПРОФИЛЬ-ПРИМЕР (examples/)

| Тема | references/ (durable, любая фича) | examples/citeck-ai-assistant.md (специфика citeck-ai) |
|---|---|---|
| Окружение | выбор стенда (local/удалённый), параметр `base_url` + MCP-профиль, ⚠ подтверждение окружения и защита от прода, gateway-роутинг, BASIC/OIDC auth, smoke | namespace, `./mvnw spring-boot:run`, порт, OnlyOffice/RAG (специфика локального citeck-ai) |
| Инструменты | теги, общий `<base_url>/gateway/<svc>/...` harness (base_url из выбранного стенда), async-polling, jq | `/api/assistant/universal/async`, `/bpmn/async`, action-id whitelist, chat-контракт |
| Records API | паттерны query/mutate, `_workspace`-правила, `language: predicate`, антипаттерны | типы temp-file/doclib/ai-agent, verify pending-file |
| Playwright | auth bootstrap, network-flow, console/network-чек, ref-instability/overlay workaround | селекторы `.ai-assistant-chat__*`, agent-dropdown, file-upload, clear-context |
| Структура | tier A/B, кластер-модель, ID-конвенции (T/S/R/F/I/C), done-criteria | конкретные 6 кластеров COREDEV-159, агенты-под-кейсы |
| Отчётность | шаблон отчёта, таблица дефектов, verdict-гейт | — |

## SKILL.md — frontmatter и flow

**Frontmatter:**
```yaml
---
name: citeck-test-feature
description: "Plan and run acceptance testing for a new Citeck platform feature on a chosen stand. Scaffolds a dated test-plan folder (cases/reports/subagent-prompts/test-data), uses Citeck MCP + Playwright MCP + scripted HTTP, and lays cases out across tiers and config clusters. Use when the user wants to test/QA a new Citeck feature, branch, or tracker issue end-to-end."
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, AskUserQuestion, Agent, mcp__citeck__test_connection, mcp__citeck__list_profiles, mcp__citeck__records_query, mcp__citeck__records_mutate, mcp__citeck__search_issues, mcp__citeck__query_comments, mcp__plugin_playwright_playwright__browser_navigate, mcp__plugin_playwright_playwright__browser_snapshot, mcp__plugin_playwright_playwright__browser_click, mcp__plugin_playwright_playwright__browser_type, mcp__plugin_playwright_playwright__browser_fill_form, mcp__plugin_playwright_playwright__browser_file_upload, mcp__plugin_playwright_playwright__browser_wait_for, mcp__plugin_playwright_playwright__browser_take_screenshot, mcp__plugin_playwright_playwright__browser_console_messages, mcp__plugin_playwright_playwright__browser_network_requests, mcp__plugin_playwright_playwright__browser_evaluate, mcp__plugin_playwright_playwright__browser_run_code_unsafe, mcp__plugin_playwright_playwright__browser_close
---
```

> ⚠ **Префикс Playwright-тулов (проверено 2026-06-22).** Схема именования тула =
> `mcp__plugin_<plugin>_<server>__<tool>`. Playwright стоит как **отдельный** плагин с
> сервером `playwright` (см. `playwright/.mcp.json`) → полное имя
> **`mcp__plugin_playwright_playwright__browser_*`** (именно так тулы видны в рантайме).
> Короткая форма `mcp__citeck__*` работает **только** для собственных тулов плагина citeck
> (нормализация имени своего сервера); для **чужого** плагина playwright короткий префикс
> `mcp__playwright__*` не сматчится — нужно полное неймспейс-имя, оно и проставлено в
> `allowed-tools` выше. Без записи в allowlist Tier B и safety-verification, идущие в
> **основном** контексте скилла (pre-flight `browser_navigate`, console/network-чек), упадут на
> инвокации; внутри субагентов (`Agent`) тулсет шире, но на них полагаться нельзя.
> Финальную сверку всё равно сделать через `claude --plugin-dir` (шаг 2 в Verification),
> т.к. имя сервера в чужом плагине теоретически может смениться.

**Тело SKILL.md (RU), flow:**
1. **Сбор входных данных** (AskUserQuestion при отсутствии): фича/ветка, tracker-issue (опц.),
   целевой проект/микросервис, **целевой стенд** (local или удалённый — какой профиль/URL).
   Если задан issue — `search_issues` + `query_comments` для деталей.
2. **⚠ Safety-гейт (deny-by-default для деструктива).** `mcp__citeck__list_profiles` +
   `mcp__citeck__test_connection` → показать пользователю **фактический `base_url` + профиль**,
   зафиксировать `base_url` как переменную для всех curl/Playwright/Records-операций.
   **Защита от прода НЕ по виду URL, а по явной классификации стенда:**
   - Деструктивные операции (`records_mutate`, очистка тест-данных, рестарт сервиса, патч
     конфигов/`application.yml`) **запрещены по умолчанию** и разрешаются только если стенд
     **явно помечен как non-prod** — через декларацию в стенд-политике (см. ниже) или метаданные
     профиля. Не угадывать по hostname: алиасы, скопированные профили, общие QA-тенанты и
     прод-данные за непрод-именем обходят эвристику.
   - **Fail-closed:** при неизвестной/неподтверждённой классификации стенда — **стоп**, не
     «спросить и продолжить». Read-only кейсы (`records_query`, GET-эндпоинты, Playwright-навигация
     без мутаций) допускаются после подтверждения окружения.
   - **Обязательный scoping:** все мутации привязаны к выделенному тестовому
     `workspace`/tenant + уникальному `run-id`, чтобы писать только в свою песочницу и не
     задеть чужие данные на общем стенде.
   - **Стенд-политика:** скилл читает checked-in декларацию (напр.
     `<project>/docs/plans/.test-stands.yml` или секцию в `references/environment.md`) вида
     `{<profile>: {classification: local|qa|staging|prod, destructive_allowed: bool, allowed_workspaces: [...]}}`.
     Кластер-кейсы с рестартом/патчем конфига — только на стендах, где это разрешено политикой
     (по сути local/выделенный QA, где сервис под контролем тестировщика).

   Прочитать `${CLAUDE_SKILL_DIR}/references/environment.md`.
3. **Загрузка durable-контекста:** прочитать нужные `references/*`; если тестируется
   AI-ассистент — `examples/citeck-ai-assistant.md` как профиль-пример.
4. **Скоупинг кейсов:** по диффу ветки / design-доку / описанию issue выделить новое;
   разложить по tier'ам (A=API-параллельно, B=UI-последовательно) и кластерам (минимизация
   рестартов); присвоить ID (T/S/R/.../C).
5. **Скаффолдинг папки** в `<project>/docs/plans/<YYYY-MM-DD>-<issue>-test-plan/` из
   `templates/`: README, cases/, reports/<date>.md, subagent-prompts/, при нужде test-data/
   (через `scripts/`). **Идемпотентность (защита от затирания):**
   - Корень плана создаётся **эксклюзивно** (create-only). Если папка уже существует —
     не перезаписывать молча: предложить `--resume` (дописать недостающее) либо новый прогон.
   - **Не перезаписывать не-плейсхолдерные файлы** (отредактированные cases/README/subagent-
     prompts): затираем только файлы, оставшиеся в шаблонном состоянии; изменённые — пропуск
     с предупреждением.
   - Каждый прогон/отчёт пишется под **уникальным run-id** (timestamp/иниц.) —
     `reports/<date>-<run-id>.md` (а не один общий `<date>.md`), чтобы повторный запуск в тот
     же день или второй оператор не затёрли аудит-трейл приёмки.
6. **Pre-flight:** smoke стенда (containers/порт/availability), генерация test-data.
7. **Прогон:** оркестрация субагентов — tier A параллельно (внутри кластера), tier B
   последовательно (один браузер), кластеры последовательно; после каждого — дописывать
   отчёт; ⚠ return-to-defaults после кластеров с патчем конфига.
8. **Отчёт и гейт:** заполнить summary/дефекты/verdict; не отмечать готовым до прохождения
   done-criteria.

В тело включить компактную «оркестратор-памятку» и таблицу «Что делать если …»
(как в README COREDEV-159).

## Файлы к созданию/изменению

**Новые (в `plugins/citeck/skills/citeck-test-feature/`):** `SKILL.md`, шесть `references/*.md`,
`examples/citeck-ai-assistant.md`, шесть `templates/*.md`, три `scripts/*.py`
(скопировать из `test-data/generators/`, они платформо-агностичны).

Контент `references/*` — обобщить из `runbook/*`, вычистив COREDEV-159-конкретику
(workspace `test-coredev-159`, конкретные агенты, 6 кластеров) → она уходит в `examples/`.
**Особо в `environment.md`:** описать выбор стенда (local + удалённый), параметр `base_url`,
матрицу профилей/auth (BASIC для local, OIDC для удалённых), и **стенд-политику**
(deny-by-default деструктива, классификация стенда, fail-closed, workspace/run-id scoping) —
БЕЗ хардкода `localhost`. Привести формат декларации стендов (`.test-stands.yml` /
секция-таблица) и пример: `local` → `destructive_allowed: true`; удалённый QA →
по явному разрешению; всё неизвестное → запрет мутаций. Также задокументировать **точные имена
Playwright-тулов** в рантайме плагина (из `claude --plugin-dir`-проверки) — чтобы `allowed-tools`
и runbook ссылались на верный префикс.

**Изменения в репозитории плагина (интеграция нового скилла):**

| Файл | Изменение |
|---|---|
| `plugins/citeck/.claude-plugin/plugin.json` | bump `version` 3.8.0 → 3.9.0 |
| `RELEASE_NOTES.md` | секция новой версии: добавлен скилл `citeck-test-feature` |
| `README.md` | добавить скилл в список skills/usage |
| `CLAUDE.md` (репо) | дописать `citeck-test-feature` в «Skill definition format» |

`_shared/` не трогаем (task-description-guide не релевантен). MCP-сервер/`lib/` — без изменений.

## Memory

Добавить memory-заметку (`reference`): где живёт скилл (`citeck-claude-code-tools` →
`plugins/citeck/skills/citeck-test-feature`) и что план COREDEV-159 — его референс-реализация.
Дописать строку в `MEMORY.md`. Существующую `future-config-generation-agent.md` не трогаем.

## Verification

1. **Структура/frontmatter:** `find plugins/citeck/skills/citeck-test-feature -type f` —
   все файлы; YAML-frontmatter валиден, `name` == имя папки; **`allowed-tools` содержит и
   citeck-, и Playwright-тулы** под подтверждённым префиксом (распарсить frontmatter и сверить
   с тулами, реально вызываемыми в SKILL.md/runbook — ни один используемый тул не должен
   отсутствовать в allowlist).
2. **Локальный запуск плагина:** `claude --plugin-dir ./plugins/citeck` → скилл виден как
   `/citeck:citeck-test-feature`, описание триггерит на «протестировать новую фичу Citeck».
   Здесь же зафиксировать **фактический префикс Playwright-тулов** и прогнать один
   `browser_navigate` + console/network-чек **из контекста скилла** (не субагента) — убедиться,
   что allowlist не блокирует Tier B.
3. **Сухой прогон скаффолдинга + идемпотентность:** вызвать на тестовом issue/ветке citeck-ai
   → создаётся `docs/plans/<date>-<issue>-test-plan/` с README+cases+reports+subagent-prompts,
   плейсхолдеры заполнены. **Повторный вызов** на тот же issue → корень не затирается:
   отредактированные файлы сохранены, новый отчёт лёг под отдельным `run-id`.
4. **Safety-гейт (deny-by-default):** flow дергает `list_profiles`/`test_connection`, показывает
   `base_url`+профиль; **на стенде без явной non-prod-классификации мутации заблокированы**
   (fail-closed), read-only — после подтверждения. Проверить три сценария: (а) local с
   `destructive_allowed: true` → мутации идут; (б) удалённый неклассифицированный → стоп перед
   первым `records_mutate`; (в) harness использует `<base_url>`, а не localhost (curl/Playwright
   бьют в правильный URL удалённого стенда).
5. **Скрипты фикстур:** `python3 .../scripts/make-images.py` в temp-каталоге → валидные PNG
   (PIL `size`/`mode` корректны).
6. **Сравнение с эталоном:** сгенерированная структура совместима с реальным
   `2026-05-07-coredev-159/` (тот же набор разделов в README и отчёте).
7. **Регрессия плагина:** `cd plugins/citeck && uv run python -m pytest tests/ -v` —
   существующие тесты зелёные (новый скилл их не ломает).
