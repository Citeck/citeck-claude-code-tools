# Example Profile: AI-ассистент citeck-ai (COREDEV-159/313)

ПРОФИЛЬ-ПРИМЕР — специфика тестирования AI-ассистента в `citeck-ai`. Показывает, как durable-ядро
(`references/*`) кладётся на конкретную фичу. **Это пример, а не часть durable-методологии** —
другие фичи заведут свой профиль. Референс-реализация: `citeck-ai/docs/plans/2026-05-07-coredev-159/`.

> **Volatile snapshot:** endpoints, actions, models, limits and selectors below are discovery hints,
> not source of truth. Before every new plan inventory current controllers/tools/config/UI and record
> the tested commit in `surface-inventory.tsv`. Never copy a hardcoded HITL action without reading
> the current response `actions[].id`.

## Окружение (специфика citeck-ai local)

- Стенд: `citeck_*_<namespace>_default` (docker), citeck-ai запускается **локально через Maven**:
  `./mvnw spring-boot:run -Dspring-boot.run.profiles=dev,dev_local` (MCP profile `local`), порт **8613**.
- ⚠ `docker logs citeck-ai` НЕ работает — сервис вне контейнера. Лог:
  `./mvnw spring-boot:run 2>&1 | tee target/logs/citeck-ai.log` (или `/tmp/citeck-ai.log`, если
  планируется `mvn clean`). Stdout агрессивно буферизуется — readiness проверять через
  `lsof -iTCP:8613` / curl ping, не grep по логу.
- Внешние сервисы: OpenAI (`gpt-5.4` text, `gpt-image-1`/`gpt-image-2` image), Anthropic
  (`claude-opus-4-5`), RAG-service (`rag` webapp на `host.docker.internal:8614`, в ZK стенда).
- Ожидаемые webapps: `[ai, eapps, emodel, eproc, gateway, history, rag, transformations, uiserv]`.
- Локальный стенд с BASIC auth (`ENABLE_OIDC_FULL_ACCESS=false`, `BASIC_AUTH_ACCESS=admin:admin`) —
  `-u admin:admin` достаточно, Playwright-cookie не нужен. Классификация: `local`,
  `destructive_allowed: true`, workspace `test-coredev-159`.

## HTTP-эндпоинты ассистента (service `ai`)

`BASE=<base_url>/gateway/ai`

| METHOD | Path | Назначение |
|---|---|---|
| `POST` | `/api/assistant/universal/async` | Async-запрос (chat, draft, business-app, file/image) |
| `GET`  | `/api/assistant/universal/{requestId}` | Polling статуса |
| `DELETE` | `/api/assistant/universal/{requestId}` | Отмена |
| `DELETE` | `/api/assistant/universal/conversation/{conversationId}` | Clear-context |
| `POST` | `/api/assistant/bpmn/async` | **Прямая BPMN-генерация/Q&A** (отдельный controller, timeout 10 мин) |
| `GET`/`DELETE` | `/api/assistant/bpmn/{requestId}` | Polling/отмена BPMN |
| `DELETE` | `/api/assistant/bpmn/conversation/{conversationId}` | Clear BPMN conversation |
| `POST` | `/api/assistant/send-mail` | Отправка email |
| `GET`  | `/api/assistant/availability` | Health-check (Boolean) |
| `GET` | `/api/ai-agent/list` | Список доступных агентов |
| `GET` | `/api/ai-agent/available-providers` / `available-tools` | Провайдеры / тулы |
| `POST` | `/api/ai-agent/execute` | Прямое исполнение user-defined агента |
| `GET` | `/api/call-recording/config` / `records` | Recording config и ACL-aware records |
| `POST` | `/api/call-recording/session/start` | Старт owned recording session |
| `POST` | `/api/call-recording/session/{id}/chunks` / `end` | Upload chunks и запуск обработки |
| `GET` | `/api/call-recording/session/{id}/status` | Owned processing status |

⚠ Business-app генерация — НЕ отдельный endpoint: через `universal/async` с
`detectedIntent=BUSINESS_APP_GENERATION` (распознаётся из текста). BPMN-генерация — отдельный
endpoint (`/api/assistant/bpmn/async`), universal-чат BPMN напрямую не генерирует.
⚠ Universal timeout — **30 минут** (`REQUEST_TIMEOUT_MINUTES`).

### Контракт `context` (проверено сетевым трейсом UI)

```json
{
  "message": "Что в этом документе?",
  "conversationId": "<uuid>",
  "context": {
    "workspace": "user$admin",
    "selection": {"records": [], "attributes": [], "documents": []},
    "content": {"documents": [{"recordRef":"emodel/temp-file@<uuid>","name":"sample.pdf","size":612,"type":"application/pdf"}]},
    "forceIntent": null,
    "agentRef": "emodel/ai-agent@<id>"
  },
  "action": "<exact current actions[].id>"
}
```

Различение полей в `context`:
| Поле | Назначение |
|---|---|
| `content.documents[]` | Uploaded файлы (через `/api/ecos/webapp/content`) |
| `contextArtifacts[]` | @-mention'ы существующих ECOS-записей |
| `selection.records[]` | Текущая selection в редакторе/списке |

`workspaceId`/`mentionedRecords` — НЕ top-level поля API.

### Action contract

Action IDs belong to different state machines: plan, deploy, mutation, file/image save and
escalation. Always take the exact value and case from the latest `result.actions[]`; send it as a
top-level request field with the same `conversationId`. A label such as «Подтвердить» is not an API
ID. Record current IDs and owning source code in the plan inventory instead of maintaining a static
whitelist in this example.

### File upload контракт
У ассистента НЕТ своего multipart-эндпоинта. Двухшаговый flow: (1) `curl -F "file=@..."
<base_url>/gateway/emodel/api/ecos/webapp/content` → `{"entityRef":"emodel/temp-file@<uuid>"}`,
(2) ref в `context.content.documents[]`. UI accept-list:
`.pdf,.docx,.txt,.doc,.rtf,.bpmn,.xml` — ⚠ **изображения через UI не грузятся** (backend
`analyzeFile` их поддерживает, но `accept` не включает image/*) → image-через-analyzeFile только
через scripted HTTP.

## Playwright: селекторы чата (CSS, BEM)

| Что | Селектор |
|---|---|
| Триггер открытия | `.ecos-model-editor__designer-ai-button` |
| Текстовое поле | `.ai-assistant-chat__input` (placeholder «Опишите, что вы хотите создать...») |
| Workspace-tag | `.ai-assistant-chat__context-tag--workspace` |
| Agent-tag / dropdown | `.ai-assistant-chat__context-tag--agent` / `.ai-assistant-chat__agent-dropdown` |
| File-upload | `.ai-assistant-chat__floating-action--file-upload` |
| Clear-context | `.ai-assistant-chat__floating-action--clear-context` |
| Сообщения user/AI | `.ai-assistant-chat__message--user` / `--ai` |
| Закрыть/свернуть | `.ai-assistant-chat__close` / `__minimize` |

⚠ **Clear-context** = новая conversation без закрытия чата (правильный способ начать новый кейс;
close+reopen НЕ сбрасывает conversationId). **Switch agent сбрасывает диалог и uploaded files** →
всегда **сначала агент, потом файл**. Action-кнопки (CONFIRM/Отменить/new_record) рендерятся внутри
`.ai-assistant-chat__message--ai` — брать по тексту/`ref` из свежего snapshot. Якорь для
`browser_wait_for`: текст «Citeck AI» (имя агента в таге) или placeholder.

## User-defined агенты на стенде (snapshot — ID меняются между стендами!)

⚠ ID агентов (`c1b845b7-…`, `95465845-…`, …) меняются между стендами. На свежем стенде —
переоткрыть через Records API, не доверять снимку:
```python
mcp__citeck__records_query(
  query={"sourceId":"emodel/ai-agent","language":"predicate","query":{}},
  attributes=["id","name","providerType","modelName","temperature","tools[]?str","instruction"])
```

| Назначение | Агент (по роли) |
|---|---|
| Полный file/image whitelist (F/I-кейсы) | «Тест: файловые инструменты» (`proposeFile`,`analyzeFile`,`generateImage`,`editImage`,…) |
| Combined image+CRUD | «Агент ландшафтного дизайна» |
| Whitelist gating (агент **без** proposeFile) | минимальный агент (только `getRecordAttributes`+`getCurrentTime`) |
| Anthropic native PDF/DOCX/images | агент на `claude-opus-4-5` (multimodal) |
| Custom agent + @-mention документа | «Помощник по задачам и документам» (`ragSearch`,`documentAnalysis`,…) |

Возврат на встроенного «Citeck AI»: открыть agent-dropdown → первый пункт («Universal assistant»);
в POST `agentRef` пропадает.

## Кластеры конфигов COREDEV-159 (6 шт. — конкретика этой фичи)

| # | Конфиг | Что меняется |
|---|---|---|
| 0 | Pre-flight + unit | — |
| 1 | Default | дефолт |
| 2 | multimodal off | `citeck.ai.multimodal.enabled=false` |
| 3 | image off | `citeck.ai.image.enabled=false` |
| 4 | size + rate limits | `multimodal.limits.max-file-size-mb=2`, `image.openai.limits.max-generations-per-conversation=3` |
| 5 | gpt-image-2 | `citeck.ai.image.openai.model=gpt-image-2` |
| 6 | TTL=1m (patch+ребилд) | `PendingFileSave.EXPIRY_MS = 1m` |

⚠ После кластера 6 восстановить captured config/source backup только если test-patched checksum не
изменился. Итоговый diff должен совпасть с pre-run baseline; destructive Git restore запрещён.

## Verify-снайпеты (специфика)
- temp-ref удалён после save: `records_query` на `emodel/temp-file@<id>` → `_notExists?bool == true`.
- «AI Generated» folder: найти через `emodel/doclib` (name=«AI Generated» + `_workspace`), при
  invalidate-сценарии удалить — следующий save пересоздаёт через `imageTargetResolver`.
- PIL-verify сгенерированных изображений: скачать preview-URL из network → `python3 + PIL`
  (`size`/`mode`/alpha для transparent PNG).
