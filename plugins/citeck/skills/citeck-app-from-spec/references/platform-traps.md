# Ловушки платформы Citeck ECOS при записи артефактов приложения

Справочник для внешнего агента (Pi / Claude Code), который пишет артефакты приложения файлами в раскладке `ecos-apps` (`meta.json` + `artifacts/<вид>/...`) и разворачивает архив в ОДНО рабочее пространство. Здесь только факты о платформе, а не о внутреннем ассистенте.

Составлен 2026-11-10 по источникам (каталог `citeck-ai/docs/`):
- `plans/20261106-app-generation-to-external-agents/`: `plan-2026-4-section2-by-engine.md` (раздел «Платформенные факты и ловушки»), `inventory-bpmn-dmn-script.md` (§3.4), `inventory-datatype-perms-patch.md` (§3.4, §3.5), `inventory-ui-artifacts.md` (§5.4), `inventory-crosscutting.md`;
- `tests/ai-assistant-regression/reports/2026-11-06-crm-gen-compare/`: `LIST-TRAP.md`, `COMPARE.md`, `deploy/gpt-fixes.txt`, `deploy/deepseek-fixes.txt`.

Факты могут устареть при смене версии платформы: перепроверяйте их при обновлении. Всё равно проверяйте результат на стенде (чтение записи обратно, открытие формы и журнала, запуск процесса): справочник не заменяет проверку.

Столбцы: «Дефект-источник» — идентификатор дефекта или файл, как он указан в источнике; «ТЗ» — на каком прогоне факт выявлен: `crm-spec-v5` (прогоны по ТЗ CRM), `unknown` (источник не называет прогон; факт взят из правил промптов и схем, закодированных по прошлым дефектам). «гипотеза» — не подтверждено проверкой.

## 1. Тип данных (`model/type`)

| Факт | Дефект-источник | ТЗ |
|---|---|---|
| Корневой `id` в YAML типа пишите БЕЗ префикса пространства. С префиксом запись идёт по пути создания и падает с «source id already registered». Итоговый id типа в пространстве: `<ws>:<id>`. | `DataTypeNormalizer`; `inventory-datatype-perms-patch.md` §3.5 | unknown |
| Файл (вложение) — атрибут типа `CONTENT`, не `BINARY`. Менять тип существующего атрибута у типа с записями нельзя: платформа данные не конвертирует. | `model-type-schema-compact.yml:50-52`; `DataTypeAttributeTypeGuard` | unknown |
| `computed.storingType` — сосед `computed.config`, а не ключ внутри него. Внутри платформа его не читает и считает атрибут на каждом чтении. Хранимый атрибут типа с записями нельзя сделать вычисляемым на чтении. | `data_type_generation_prompt.xml:75-81` | unknown |
| Скрипт вычисляемого атрибута работает на GraalJS без доступа к Java (`java.*`, `Packages.*`, `Java.type` не существуют). Значение считается на ЧТЕНИИ: ошибка ломает открытие каждой записи. | там же, `:111-113` | unknown |
| В скрипте доступны `value` (только чтение: `value.load('…')`, `getId()`, `getRef()`, `getLocalId()`) и `Records`. `value.att(...)` и `value.save()` падают с «Mutation does not support»; `value.att('x')` с одним аргументом даёт «Arity error». | там же, `:118-122` | unknown |
| `computed.config.fn` — тело функции с `return`. Обёртка `function(value){…}` — синтаксическая ошибка или не вызывается. | там же, `:123-125` | unknown |
| `storingType`: `NONE` — на каждом чтении; `ON_CREATE` — один раз; `ON_EMPTY` — пока пусто; `ON_MUTATE` — на каждом сохранении. Дата разового события — `ON_EMPTY` со скриптом, возвращающим дату только на нужном статусе. | там же, `:130-141` | unknown |
| Системные атрибуты: статус — `_status` (не `status`); дата входа на текущий этап — `_statusModified`; дата создания — `_created`; автор — `_creator`; номер записи — `_docNum`. Не объявляйте их в типе и не выдумывайте `createdAt`. Поле вычисляемого атрибута читает только существующие атрибуты: `status?str` вместо `_status?str` молча даёт пусто. | `:139,147,148`; smoke1007 CLOSE-DATE-WRONG-ATT; F-b-COND-MISSING-ATTR; 2.12.4, W-IC | unknown |
| `dispNameTemplate` не ссылайтесь на `${_docNum}` без собственного `numTemplateRef`: у базовых типов шаблона нет. Ассоциация в шаблоне показывается через `?disp`; `?str` даёт id записи. | `:164,182` | unknown |
| `config.unique: true` — единственный способ задать уникальность, только для TEXT. | `:230-232` | unknown |
| Тип со статусами обязан иметь корневой `defaultStatus`, иначе записи создаются без статуса. | `:247` | unknown |
| Платформа отклоняет тип, где один статус сгруппирован в несколько этапов: «exists in multiple stages». | Н18-2 | unknown |
| Обязательный атрибут без «наполнителя» ломает создание записи (`500 Mandatory attributes are empty`). Рецепты автозаполнения: `_creator?id` с `ON_CREATE`; путь через связанную запись (`…manager?id`) с `ON_EMPTY` и БЕЗ `mandatory`. Рецепт `ON_EMPTY` через ассоциацию проверен только для `emodel/person.manager`; на пути `deal.responsibleManager?id` при создании даёт пусто (гипотеза, что причина в порядке вычисления). | `:90-110`; S-7, В8 | crm-spec-v5 (В8: CRM1) |
| Роли живут в `model.roles`. Роль привязывается к атрибуту РОВНО одного типа PERSON / AUTHORITY / AUTHORITY_GROUP: над TEXT роль не разрешается ни в кого. Статический `GROUP_…` нельзя выводить из описательного имени. Роль «Администратор» нельзя привязывать к `GROUP_EVERYONE`. Id роли следует русскому названию. | `:458-465,468,489,515` | unknown |
| Роль активности считается по employee, а не по сделке; рецепт для роли по связи сделки не подтверждён. | S-7, В8 | crm-spec-v5 |
| Новый тип не наследует от другого типа; родитель допустим только `case` или `data-list`. | `:671` | unknown |
| Список глобальных справочников нельзя получить признаком родителя `data-list` (395 типов); `sourceId` справочника пропадает после патча. Встроенные сущности ecos-model (`has-documents`, `has-internal-comments`, working-calendar/schedule, канбан) подключаются каждая своим способом. | файл справочников (план 2026.4, раздел P) | crm-spec-v5 |
| Поле rich text (`lexical`) хранится как HTML и выводится сырым в журнале, письме и тексте. | 2.12.5 | crm-spec-v5 |
| Закрытое поле (`disabled` и `persistent: false`) не отправляется при сохранении; поле «Причина», закрытое `disabled`, не пишется формой, а проверка этапа, требующая такое поле, даёт тупик. | D-15, D-18; 2.12.1, В9, ENT2-S3 | crm-spec-v5 |
| Комментарий к задаче хранится на задаче и сам не переносится в поле записи (например `reason`): перенос нужно писать явно скриптом процесса. | 2.12.1, В9, SPEC*-REASON-NOT-STORED | crm-spec-v5 |

## 2. Матрица прав (`model/permissions`, записи `emodel/perms`)

| Факт | Дефект-источник | ТЗ |
|---|---|---|
| Вид артефакта называется `model/permissions`, а sourceId записей — `emodel/perms`. Id матрицы нового типа — `<typeLocalId>-permissions`; при правке сохраняйте id, иначе появится вторая конкурирующая матрица. В пространстве запись адресуется `emodel/perms@<ws>:<id>`; id идёт только в ref, не в поле DTO. | `permissions-schema-compact.yml:6-7`; `type_perms_generation_prompt.xml:143-146`; `TypePermsGenerationService.kt:938-991` | unknown |
| `ANY` в матрице только ПОДНИМАЕТ доступ (ячейка статуса объединяется с `ANY`). Неустановленная ячейка равна READ, а не «нет доступа». `ANY: NONE` без раскрытия по статусам ничего не закрывает и не закрывает запись без статуса; для записи без статуса нужен `EMPTY`. | `:33-43,68`; V6a, Н18-6, SP3-3 | unknown |
| В списке `statuses` правила слово `ANY` сравнивается буквально и не срабатывает никогда; нужен пустой список `[]`. | `:44-46` | unknown |
| Права выдаются РОЛИ. Придуманная роль никому ничего не даёт и выглядит как рабочее правило. Роль, которой нет в матрице, доступа не получает; без матрицы участники пространства читают. | `:47-49`; V5-A6 | unknown |
| «Только чтение» — это READ, а не NONE (NONE прячет запись). Голый `NONE` на этапе при обещании «только чтение» — ошибка. `REVOKE WRITE` над ячейкой NONE ничего не отбирает. `EVERYONE` с READ открывает запись не-участникам. | `:70-73`; SP3-3 | unknown |
| Платформа ничего не подставляет в условие правила: `$user`, `$CURRENT`, `${user}` сравниваются как текст. `_status` в условии читается как отображаемое имя; статусы задавайте в `statuses`. | `:86-100` | unknown |
| Непустой `attributes` — закрытый список: каждое неназванное поле станет только для чтения, запись в него молча отбрасывается. Запись в поле работает, только если роль может писать и запись целиком. Отдельного права «удалять» нет. | `:101-129`; `permissions-schema-compact.yml:104` | unknown |
| После расширения матрицы старые записи открываются по ссылке, но не видны в поиске и журналах до пересохранения (`queryPermsPolicy OWN`). | V6-OLD-RECORDS | unknown |
| Права на одну запись (`emodel/permission-settings`): `version` не задавайте; платформа молча отбрасывает обновление с версией не больше хранимой. Создание — через исходный ref с пустым локальным id, обновление — по полному ref (не upsert). Записывать может только администратор. | `permission-settings-schema-compact.yml:49`; `PermissionSettingsGenerationService.kt:292-300`; `AdminOnlyArtifactGate` | unknown |

## 3. Шаблон нумерации (`emodel/num-template`)

| Факт | Дефект-источник | ТЗ |
|---|---|---|
| Поле `name` в YAML шаблона нумерации — простая строка, не объект `{ru,en}`; иначе развёртывание не проходит (правилось вручную на двух приложениях). | `deploy/gpt-fixes.txt`, `deploy/deepseek-fixes.txt` | crm-spec-v5 |
| Авто-нумерация: атрибут `computed.type: COUNTER`, `numTemplateRef: emodel/num-template@<id>-num-template`, `storingType: ON_CREATE`. Недостающий шаблон создаёте в том же пространстве. Формат («З-1») — это `dispNameTemplate` над счётчиком, а не сам счётчик. | `data_type_generation_prompt.xml:197-212` | unknown |
| У типа с тип-уровневым `numTemplateRef` нумерует `_docNum`: счётчик рядом сжигает два номера на запись. Номер в выводе — `_docNum`, а не счётчик типа. | `NumberingPromiseEnforcer` (KDoc); 2.12.4 | crm-spec-v5 |
| `emodel/num-template` — не upsert: обновление по полному ref, создание через исходный ref с пустым локальным id. | `inventory-datatype-perms-patch.md` §3.4 | unknown |

## 4. Форма (`ui/form`)

| Факт | Дефект-источник | ТЗ |
|---|---|---|
| Id формы — без префикса пространства. | `FormIdWorkspacePrefix` (источник инвентаря) | unknown |
| `data` формы содержит только значения собственных компонентов по `key`. Условие читает только такие ключи или `_status` (его добавляйте скрытым непостоянным компонентом). | `form-components-reference.yml:717-718,750` | unknown |
| `validate.custom` на необязательном пустом поле не выполняется; «обязательно, если заполнено другое» — только через `conditional_required`. | `:563-565` | unknown |
| `modalTitle` — строка, не `{ru,en}`. `journalId` у picker-компонентов задавайте явно. `att` в `customPredicateJs` — атрибут ЦЕЛЕВОГО типа. `queryData` — не фильтр. | `:223,228,232,234` | unknown |
| Файловое поле над `CONTENT`: `multiple: false` (при `multiple: true` теряется второй файл). Поле `ASSOC` без `journalId` ломает форму. | `:278`; V3, I-b-ASSOC | crm-spec-v5 |
| Черновик — системный флаг записи, не статус: submit с `state:"draft"` не проверяет обязательные поля и не запускает процесс. | `:401-404` | unknown |
| Скрываемому условием полю нужен `clearOnHide: false`, иначе значение стирается; `textarea` нельзя класть в `columns`. | `:1187,1323` | unknown |
| Закрытое поле (`disabled`, `persistent: false`) в форме не сохраняется (см. раздел 1). | D-15, D-18 | crm-spec-v5 |
| Новая форма или журнал не берёт id существующей записи. Окно формы в ecos-ui открывается по `formId`; со ссылкой `formRef` молча открывается форма типа по умолчанию. | `NewViewArtifactIdGuard`; acc1016 | unknown |

## 5. Журнал (`ui/journal`) и настройки журнала

| Факт | Дефект-источник | ТЗ |
|---|---|---|
| `t` предиката только из списка: `and, or, not, eq, gt, ge, lt, le, like, in, contains, empty, starts, ends`; иное платформа читает как «нет записей». | `journal-schema-compact.yml:98-101` | unknown |
| `_stage` допустим только у типа со стадиями. Действия журнала — только ссылки на существующие действия. | `:82-85,125-126` | unknown |
| Id колонки = id атрибута, тип колонки = типу атрибута. Пустой `defaultSortBy` противоположен платформенному `_created desc`. | `:45,63`; `JournalGenerationService.kt:248` | unknown |
| Поиск по тексту для колонки-связи требует `searchConfig.searchByText.innerQuery`. | D-16 | crm-spec-v5 |
| Настройка журнала отвечает на ОДИН вопрос; колонки журнала не копируйте ради сортировки; группы доступа не угадывайте. | `journal-settings-schema-compact.yml:45-47,100-104` | unknown |
| Тип пространства не получает журнал или пункт меню над глобальным типом. | 2.10, 2.3 | crm-spec-v5 |

## 6. Действие (`ui/action`)

| Факт | Дефект-источник | ТЗ |
|---|---|---|
| `create` всегда открывает форму. Ключи чужого вида действия молча игнорируются. `config.attributes` — только реальные атрибуты. | `action-schema-compact.yml:52-53,78-80` | unknown |
| Статус в `predicate` — как `_status?str` и существующий; `execForQuery` не ставьте. | `:91-92,113-114` | unknown |
| В пространстве нет действий `mutate _status` и `user-event`; кнопка смены этапа из пространства запрещена платформой, «Создать активность» в пространстве — ограничение платформы. Действия в пространстве записывает администратор или менеджер пространства. | `WorkspaceActionPolicy`; SPEC*-CREATE-ACTIVITY, Н7-А | crm-spec-v5 |
| Поле `_workspace` у действия требует uiserv не ниже 2.41; `moduleId` записывается последним. | `ActionGenerationService.kt:309,339` | unknown |
| D-36: в `ecos-uiserv` 2.41.0–2.41.1 теряется `attributesMapping` при записи действия с формой; исправление `24d56afb` (COREDEV-667) на момент составления не выпущено. Не полагайтесь на `attributesMapping` без проверки на стенде. | D-36 (`COMPARE.md` §6) | crm-spec-v5 |
| Эталон смены этапа в ecos-crm: граничное событие `RECORD_STATUS_CHANGED` и действие `deal-change-status`. | пакет вопроса 3 (план 2026.4) | crm-spec-v5 |

## 7. Карточка (`ui/dashboard`)

| Факт | Дефект-источник | ТЗ |
|---|---|---|
| Платформа хранит реестр виджетов и раскладки по устройствам; идентичность записи — кортеж `(typeRef, appliedToRef, authority, scope, workspace)`. Карточка адресуется по ТИПУ. `workspace` — поле DTO, не `_workspace`. | `dashboard-schema-compact.yml:4-9`; `DashboardGenerationService.kt:51,501-514` | unknown |
| `doc-preview` — только при наличии `CONTENT`. Один виджет не ставьте на две вкладки. | `:104-105,157` | unknown |
| Виджет `tasks` («Мои задачи», с кнопками исходов) отличается от `current-tasks` (без кнопок). | `dashboard-schema-compact.yml` (виджеты) | unknown |
| Для виджета документов и активностей нужны аспекты типа (`has-documents`, `has-ecos-activities`). | `:124-137`; `DashboardGenerationService.kt:554` | unknown |

## 8. Доска (`ui/board`)

| Факт | Дефект-источник | ТЗ |
|---|---|---|
| Колонки доски = статусы типа; тип без статусов не годится. | `board-schema-compact.yml:37-38,88-89` | unknown |
| `hideItemsOlderThan` — ISO-8601 duration. Ссылки на журнал, форму и действия — только на существующие. | `:6-7,44-51,81-82` | unknown |

## 9. Меню и шаблон пространства

| Факт | Дефект-источник | ТЗ |
|---|---|---|
| Тип пространства не получает форму, журнал или пункт меню над глобальным типом (`formId`, пункт меню). | 2.10 кандидаты, 2.3 | crm-spec-v5 |
| Префикс пространства (`ws:id`) в `fileTypes` и в id модулей, а также ссылка `emodel/$typeId` для типа пространства — места, где ссылка платформы теряет или не принимает префикс; проверяйте результат чтением. | WS-PREFIX-STRIPPED | crm-spec-v5 |
| Для меню правку существующего артефакта делайте патчем (`ui/menu` — допустимый `target` патча, см. раздел 13). | `artifact-patch-schema-compact.yml` | unknown |

## 10. Шаблон уведомления (`notifications/template`)

| Факт | Дефект-источник | ТЗ |
|---|---|---|
| `name` — простая строка. Каждая `${var}` должна быть объявлена в `model`, иначе Freemarker падает и письмо не уходит. Всегда пишите `${var!""}`. | `notification-template-schema-compact.yml:31,49-50,83` | unknown (имя-строка: crm-spec-v5) |
| Список для `<#list>` — только выражение с `[]`. Бины `meta`, `link` (также `image`, `config`, `_workspace`) в `model` не объявляйте. | `:63,69-73` | unknown |
| `${webUrl}` ломает рендер; ссылка на запись — только `${link.getRecordLink(docRef)}`. | `:73-75` | unknown |
| Модель уведомления загружается без языка письма: статус и тип сделки выводятся английскими значениями. Берите отображаемое имя, а не id или английское значение. | 2.12.4, D-14, CRM1-MAIL-EN-VALUES | crm-spec-v5 |
| `notifications/template@` — не upsert (создание через исходный ref с пустым локальным id). | `inventory-ui-artifacts.md` §5.4 | unknown |

## 11. Процесс BPMN (`eproc/bpmn-def`)

| Факт | Дефект-источник | ТЗ |
|---|---|---|
| `boundaryEvent` — брат задачи на уровне процесса, не ребёнок `userTask`. Двойное экранирование `&amp;quot;` ломает разбор JSON в `ecos:*`; используйте `&quot;`. | `generate_bpmn_prompt.xml:27-29` | unknown |
| На `bpmn:definitions` обязательны `ecos:defState`, `ecos:enabled`, `ecos:autoStartEnabled`, `ecos:processDefId`, `ecos:ecosType`. `ecos:processDefId` и `id` процесса держите равными. У каждой задачи — `name` и `ecos:name_ml`; процесс — непустое имя в обоих. Диаграмму (`bpmndi`) раскладка платформы строит сама. | `:56-60`; `example-bpmn.xml`; `BpmnProcessDefIds` | unknown |
| Исполнитель `userTask`: непустой `ecos:assignees` с id ролей из `model.roles`. Общей роли-запасного варианта нет, `initiator` — обычная роль типа; неизвестная роль даёт пустой список («задача ни у кого»). Режим «инициатор» — `ecos:manualRecipientsMode="true"` и `${workflowInitiator}`. Без объявления разрешается только `EVERYONE`. | `:75-81` | unknown |
| Исполнители задач вычисляются один раз при создании и не пересчитываются при смене ответственного. | S-8, G6a-REASSIGN-TASK-STAYS | unknown |
| `durationType: BUSINESS` требует `workingSchedule` (по умолчанию `emodel/working-schedule@DEFAULT`). `duration` — только часы и минуты (ISO 8601); задавайте `duration` ИЛИ `workingDays`. | `:87-88` | unknown |
| Смена статуса — отдельная `bpmn:task` с `ecos:taskType="setStatus"`; id статуса копируйте символ в символ; нужны непустые `name` и `ecos:name_ml`. Скрипт, бросающий исключение при входе на этап, отменяет завершение пользовательской задачи (синхронно). | `:92`; `BpmnStageEntryChecks` | unknown |
| `ecos:outcomes` обязателен (иначе «Task outcomes cannot be empty»). Ветка после задачи с несколькими исходами: `conditionType="OUTCOME"` и `conditionConfig.outcome="<taskId>:<outcomeId>"`. | `:95-99` | unknown |
| Параллельный шлюз: задача на ветке и проверка этапа не ставятся; `commentRequired: true` на исходах. | 2.12.2, D-03, D-09 | crm-spec-v5 |
| У каждого не-end элемента есть исходящий поток. Default-поток БЕЗ условия (иначе ENGINE-09005). | `:148-158`; правка вручную: добавлен пропущенный default-поток `R_kind->R_next` (`crmd-deal-reminders`) | unknown; crm-spec-v5 |
| Условие потока — атрибут `ecos:conditionConfig` (`SCRIPT`→`fn`, `EXPRESSION`→`expression`, `OUTCOME`→`outcome`). `bpmn:conditionExpression` при импорте не читается. Пустой `fn` при `SCRIPT` недопустим. Условное событие несёт условие на самом элементе события. | `:148-158`; `BpmnConditionalEventChecker` | unknown |
| Скрипт задачи: при ручной правке тело скрипта из `bpmn:script` скопировали в `ecos:script` (платформа читает `ecos:script`). | `deploy/deepseek-fixes.txt` | crm-spec-v5 |
| Сигнальные события: у каждого `signalEventDefinition` задавайте `id`; ссылку `signal_id` убрали (по правке вручную). Порядок дочерних элементов узла приводят к порядку схемы без смены атрибутов (правка вручную в 14 узлах). | `deploy/deepseek-fixes.txt`, `deploy/gpt-fixes.txt` | crm-spec-v5 |
| Таймер: значение только в `ecos:timeConfig` на элементе события (`DURATION` / `CYCLE` / `DATE`); дочерние `timeDuration` — только на экспорт. Выражение таймера видит только переменные процесса, не атрибуты записи: сначала копируйте дату скриптом `execution.setVariable('VAR', document.load('ATTR?str'))`. Повторяющееся напоминание — `cancelActivity="false"`; вешайте его на `userTask`, а не на set-status. | `:170-200` | unknown |
| Процесс, стартующий ТОЛЬКО таймером, не шлёт почту ролям: записи нет, роль разрешается в «никого». | `:204-208`; `BpmnTimerStartRecipientsChecker` | unknown |
| Сигнальные события записи: `ecos:eventManualMode`, `ecos:eventType` (`RECORD_CHANGED`, `RECORD_STATUS_CHANGED`, `RECORD_CREATED`, `RECORD_DELETED`, `COMMENT_*`, `USER_EVENT`), `ecos:eventFilterByRecordType` (`DOCUMENT` / `ANY` / `DOCUMENT_BY_VARIABLE`). `DOCUMENT` недопустим на собственном стартовом событии («Cannot resolve identifier 'execution'»). При автозапуске стартовое событие обычное, БЕЗ `RECORD_CREATED` своего типа (двойной запуск). `eventFilterByEcosType` — только с `ANY`. Две подписки на один сигнал в одной области сливаются в одну. | `:249-299` | unknown |
| Автозапуск: для новой записи платформа берёт ОДИН включённый процесс типа (сначала пространства, затем `default`) и запускает его, только если у него включён автозапуск. | `BpmnAutostartNeighbours` | unknown |
| Уведомления: только `bpmn:sendTask` с `ecos:notificationType="EMAIL_NOTIFICATION"`. Получатели-роли — в `notificationTo`, группы, email и пользователи — в `*ToExpression`; адреса и группы не выдумывайте. Нужен шаблон (`notifications/template@id`) с пустыми title/body ЛИБО непустое тело (иначе «Template is mandatory parameter with empty body»); минимум один получатель («All recipients is empty»). | `:316-352` | unknown |
| После рабочего финального статуса («Действует») процесс завершается; досрочное прекращение активной записи — действие записи, а не задача (иначе вечная задача у ответственного). | `:347-352` | unknown |
| AI-задача: `bpmn:task` с `ecos:taskType="aiTask"`, обязателен `ecos:aiUserInput`; ответ в переменной `aiResponse`. | `:134` | unknown |
| Исполняемая ссылка на дату входа на этап — системный `_statusModified`; в скрипте её не пишут. Для `_status`: `?disp` — имя статуса, `?str` — id; запись принимает id. | `:201-203`; `BpmnScriptStatusChecker` | unknown |
| Скрипты процесса: у `Records` ровно два метода, `get` и `query` (`queryOne` — только в вычисляемых атрибутах и ролях). Допустимые скаляры: `str, disp, num, bool, json, id, localId, assoc, raw, bin, appName, localSrcId` (`?date` нет; неизвестный скаляр молча даёт null; без скаляра читается `?disp`). Цепочка `Records.get(ref).att(...).save()` в одном выражении запрещена; создание записи (`emodel/type@`) — только в script task. | `records-script-api.md:3-47` | unknown |
| `Records.query`: источник обязателен — `ecosType: "<id типа без emodel/type@>"` (в пространстве с префиксом `ws:id`) или `sourceId`. Полный ref в `ecosType` не находит ничего и без ошибки. Результат — объект `{records, totalCount, hasMore, messages}`, не массив. | `:36-57` | unknown |
| В условии шлюза нельзя `document.att()`, `document.save()`, `execution.setVariable()` и `return` верхнего уровня. `console.*` пользователь не видит, UI показывает только значение `return`. Переменная multi-instance — Java-коллекция (ArrayList и т. п.). | `script_writing_prompt.xml:142,202,848,1213` | unknown |
| **Список, полученный от платформы (`load` с `[]`, `document.load`), в Camunda-скрипте:** `.indexOf`, `.lastIndexOf` молча дают -1, `.contains` — false (даже при наличии значения). Для вхождения используйте `.includes(...)` или `Array.from(L).indexOf(...)`; `for`, `for…of`, `.map`, `.filter`, `.some` работают. `.sort()` без аргумента и `.get(0)` на пустом списке бросают исключение; `execution.setVariable('x', L)` для такого списка не поддерживается («Save GraalVM value…»). Для `Records.query(...).records` (элементы — LinkedHashMap) `.indexOf` работает. В вычисляемых атрибутах `emodel` наоборот: `.indexOf`/`.includes` верны, `.contains`, `.size()`, `.get(0)` бросают `TypeError`. | `LIST-TRAP.md`; D-09 | crm-spec-v5 |
| Определение процесса длиннее 100 000 символов не развёртывается: `JAXP00010003 … exceeds the "100,000" limit set by "jdk.xml.maxGeneralEntitySizeLimit"`. `bpmn_validate` такой файл пропускает, ошибка видна только в `deploy_app`. Раскладка прибавляет к файлу в несколько раз больше текста, чем в нём было: держите процесс небольшим, большой делите на подпроцессы. | проверено на локальном стенде 2026-11-10 | проверка `accgen1110` |

## 12. Таблица решений DMN (`eproc/dmn-def`)

| Факт | Дефект-источник | ТЗ |
|---|---|---|
| DMN хранится как XML; `decisionId` и `decisionTableId` копируйте без изменений (процессы связываются по ним). Id записи равен `ecos:defId` внутри XML. | `dmn-ir-schema-compact.yml:1-9` | unknown |
| `sourceAtt` обязан быть реальным атрибутом типа (допустимы `?num`/`?str`): иначе переменная равна null, ни одно правило не сработает и процесс молча уйдёт по умолчанию. | `dmn_generation_prompt.xml:26-45` | unknown |
| Ячейка, начинающаяся с `=`, — «сырой» FEEL (`=> 100000`, `=[1..5]`, `=not("draft")`); без `=` значение — литерал и кавычится по типу колонки. | `:57-62` | unknown |
| `UNIQUE` строгий: при двух совпадениях Camunda бросает исключение. При пересечении диапазонов — `FIRST` и порядок от частного к общему; агрегация — только с `COLLECT`. | `:67-72` | unknown |
| Запись без `action = DEPLOY` не публикуется в Camunda. `eproc/dmn-def@` — не upsert: существующая таблица меняется через собственный ref. | `DmnGenerationService.deployDmn` | unknown |

## 13. Патч и `eapps/artifact-patch`

| Факт | Дефект-источник | ТЗ |
|---|---|---|
| `target` патча — вид из словаря ecos-apps (`model/type`, `ui/menu`, …), а не sourceId записей. Операции — закрытый словарь `add`, `set`, `remove`, `rename-key`; `add` с массивом добавляет поэлементно. `workspace` — пространство ПРАВИМОГО артефакта. Платформа применяет патч заново при каждом передеплое цели. | `artifact-patch-schema-compact.yml` | unknown |
| У патча `name` обязателен (при ручной правке добавили). | `deploy/gpt-fixes.txt` | crm-spec-v5 |
| `eapps/artifact-patch` — не upsert: обновление по полному ref, создание через исходный ref с пустым локальным id. | `ArtifactPatchGenerationService.kt:906` | unknown |
| Записи справочника заводите патчем `app/patch` типа `mutate`: порядок через `dependsOn`, однократность по id и дате патча. | «Справочник с записями» (план 2026.4) | crm-spec-v5 |

## 14. Рабочее пространство и ссылки

| Факт | Дефект-источник | ТЗ |
|---|---|---|
| Артефакт всегда принадлежит приложению; из пространства пишите только свои артефакты. Голый id приземляется как `<ws>:<id>` (личное пространство `user$x` кодируется `user__x`). Точный ref заранее может быть неизвестен: при чтении обратно перебирайте варианты. | `WorkspaceScopeResolver`; `DeployedArtifactVerifier` | unknown |
| Ссылка на свой тип внутри архива — `emodel/type@CURRENT_WS:<id>`: при загрузке в пространство платформа подставляет его id (журнал с такой ссылкой развернулся с `typeRef` `emodel/type@<ws>:<id>`). Базовые типы платформы (`data-list`, `case`) остаются глобальными. Глобальный тип и тип пространства с одним именем — разные типы. | проверено на локальном стенде 2026-11-10 (`EcosAppService.uploadZip`) | проверка `genprobe1110` |
| Глобальную запись (пустое пространство или `admin$workspace`) создаёт только запись из глобального контекста; в пространстве `PERMISSION_SETTINGS`, `TYPE_PERMS` пишет админ, `ACTION` — админ или менеджер. | `ArtifactScopeGate`; `AdminOnlyArtifactGate` | unknown |
| Форма, журнал, доска над типом вне области записи недопустимы; процесс над ПУБЛИЧНЫМ глобальным типом из пространства недопустим. Новый тип не наследует от чужого. | `TypeBoundViewGate`; `PlanNormalizers` | unknown |
| Записи, созданные до смены матрицы прав или статуса, перепроверяйте открытием по ссылке и через журнал (см. раздел 2). | V6-OLD-RECORDS | unknown |

## 15. Сквозные

| Факт | Дефект-источник | ТЗ |
|---|---|---|
| Читающие вызовы emodel синхронны без своего таймаута (readTimeout 10M): недоступность emodel и «нет атрибутов» не путайте — зависание значит сбой, а не пустоту. | winS | crm-spec-v5 |
| Записи артефактов читаются обратно как YAML; разбирайте YAML парсером, а не как JSON. В Citeck-шлюзе YAML распознаётся только после ведущей строки `---`, иначе получится текстовый узел. | `FormContentNormalizer`, DEF-F-2; CLAUDE.md citeck-ai | unknown |
| Новая запись артефакта после записи доступна не сразу: читать обратно с повторами (в ассистенте — 3 раза по 400 мс). | `DeployedArtifactVerifier` | unknown |
| Запись артефакта, изменённая кем-то после чтения базы, перезаписывать нельзя вслепую: перечитайте и объедините. | `DeployStalenessChecker` | unknown |
| `_status` читается без скаляра как `?disp`; для логики берите `?str`, для вывода — `?disp`. | 2.12.4 | crm-spec-v5 |
| Журнал, письмо и текст выводят значения: нужен отображаемый вид (`?disp`), а не id и не английское значение. | 2.12.4, D-14 | crm-spec-v5 |

## Исключено (прогоны договоров)

В источниках исключены как выявленные на прогонах договоров (ENT3 CON, `rc1017` задание 24, `BA30`, `CONTRACTS_SPEC_B`):
- `CON-STAGE-UNLINKED` (этап без статусов) — раздел 2 плана 2026.4;
- `CON-A-APPROVER-RULES-DECORATIVE` (правило согласующих не применяется);
- `CON-REWORK-REASON` (из списка 2.12.1);
- `ENT2-CON-A-ANNUL-DEAD-END` (`inventory-datatype-perms-patch.md`, строка 47);
- `ENT3-S1-TAKE-INTO-WORK-AS-OUTCOME` (2.12.2);
- `ENT3-S1-PAUSE-REJECT-DEAD-END` и `ENT3-S1` убраны из ссылок факта о причине перехода (раздел 1); сам факт сохранён по другим идентификаторам;
- `D-BA30I-LIST-REQUEST-NOT-READ-AS-JOURNAL`, `BA30h` (карточка плана при глобальном тёзке);
- `I-b-CONSENT-CONTRACT-LINK`, `ContractArtifactStepGenerator`;
- `D-BA-ROLE-GAP-DISCLOSURE-IGNORES-NEGATION` (происхождение неясно, но относится к конвейеру ассистента).

Прогоны договоров как таковые не читались: если в факте происхождение неоднозначно, он оставлен с ТЗ `unknown`.

## Отброшено как относящееся только к конвейеру ассистента

Около 150 строк-групп таблицы плана (бакеты B, A, E, M и чисто генераторные G: планировщик, карточки, состояние разговора, шаги Engine B, стражи ответа) и почти весь `inventory-crosscutting.md` (REST-слой проверок, плагин, версионирование эндпоинтов) не перенесены.
