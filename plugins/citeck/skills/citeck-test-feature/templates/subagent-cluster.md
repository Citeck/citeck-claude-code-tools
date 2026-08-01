# Subagent: Cluster <N> — <SHORT-NAME>

> Заполнить `<…>` маркеры. Для config-кластеров (2..N): `application.yml` + опц. patch + restart.
> Запускается ПОСЛЕДОВАТЕЛЬНО — кластеры строго не параллелятся.

## Задача
Прогнать кейсы кластера `<N>: <description>` после применения config-toggle.

**Метод:** mix Tier A + Tier B (зависит от кейсов). Один субагент на кластер (рестарт = дорого).
**Стенд:** `<BASE_URL>`. **Run-id:** `<RUN_ID>`.

## Pre-conditions (оркестратор делает ДО запуска субагента)
1. Применить config (см. `references/tier-cluster-model.md` → шаблон смены кластера):
   `<patch application.yml или исходника>`. ⚠ Только если стенд `destructive_allowed: true`.
2. Restart сервиса.
3. Wait ready (`lsof -iTCP:<port>` / health-check).
4. Smoke ping → ОК.

## Контекст (прочитать один раз)
1. README плана
2. Скилл `references/tier-cluster-model.md` (твой кластер `<N>`)
3. Скилл `references/tools-cheatsheet.md` / `playwright-tips.md` (по типу кейсов)
4. `cases/<нужный>.md`

## Кейсы
| ID | Tier | Из файла | Краткое описание |
|---|---|---|---|
| `<ID>` | `<A|B|A+B>` | `cases/<…>.md` | `<…>` |

## Шаги
1. Verify config применён: `grep -i "<config-key>" <log>` либо health-эндпоинт.
2. Прогнать кейсы из таблицы.
3. Соблюдать dependencies/resource locks; A+B reconciliate под одним ID.
4. Записать: `<ID>: PASS|FAIL|BLOCKED|NOT_RUN — <terminal evidence>`.

## Ограничения
- ⚠ НЕ менять config во время прогона.
- ⚠ После прогона НЕ возвращать config в default — это сделает оркестратор перед следующим кластером.
- ⚠ Для кластеров с patch исходника: после прогона `git diff <class>` показывает unmodified —
  иначе сообщить оркестратору.

## Финальный отчёт оркестратору
```
Subagent: cluster-<N>-<SHORT-NAME>  •  Run-id: <RUN_ID>
Config applied: <short summary>
Результат:
  <ID>: PASS|FAIL|BLOCKED|NOT_RUN — <terminal evidence; forbidden effects; cleanup>
Готов к переходу на cluster <N+1>.
```
