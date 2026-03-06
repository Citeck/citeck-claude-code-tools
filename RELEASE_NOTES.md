# Релизы

## v2.0.0 (2026-03-06)

Мажорный релиз — полная переработка плагина Citeck для Claude Code.

### Общие библиотеки (`lib/`)
- **config.py** — управление профилями и credentials в `~/.citeck/credentials.json` (chmod 600, валидация имён профилей от path traversal)
- **auth.py** — OIDC password grant + Basic Auth fallback + поддержка PKCE, кэширование токенов по профилям, auto-refresh, обнаружение endpoint через `eis.json` + OpenID well-known, извлечение username из JWT
- **pkce.py** — браузерный PKCE OAuth flow с локальным HTTP-сервером
- **records_api.py** — HTTP-клиент для Records API с вложенным форматом запросов (sourceId, language, consistency, workspaces, sortBy)

### Новые скиллы
- **citeck-auth** — интерактивная настройка подключения (PKCE/password/basic), тест соединения, переключение профилей
- **citeck-tracker** — управление задачами Project Tracker:
  - `query_issues.py`: поиск с `--assignee me`, `--project` (workspace), `--sort`, `--status`, `--type`
  - `create_issue.py` / `update_issue.py`: с dry-run и подтверждением
- **citeck-changes-to-task** — генерация описания задачи из git changes с возможностью создания в Citeck

### Улучшения
- Скрипты **citeck-records** теперь используют общие модули из `lib/` вместо встроенной авторизации
- Кликабельная ссылка после создания задачи

### Тесты
- 204 юнит-теста, все с моками (без обращений к реальным сервисам)

---

## v1.1.0 (2026-03-02)

### Изменения
- **citeck-records**: однострочные curl-команды заменены на Python-скрипты (`query.py`, `mutate.py`, `delete.py`) для более чистого и читаемого взаимодействия с API
- Скрипты выводят строку-сводку + форматированный JSON, а также подробные сообщения об ошибках с подсказками, когда Citeck недоступен
- Обновление README

---

## v1.0.0 (2026-02-11)

Первый релиз.

### Состав
- Структура плагина Claude Code (`.claude-plugin/plugin.json`, `marketplace.json`)
- Скилл **citeck-records** — запросы query, mutate и delete к Citeck ECOS Records API через curl
- README с инструкциями по установке и использованию
- Лицензия LGPL-3.0
