# Test Run Report: <ISSUE> — <FEATURE>

**Дата прогона:** <DATE>  •  **Run-id:** `<RUN_ID>`
**Тестировщик:** <AUTHOR>
**Окружение:** стенд `<BASE_URL>` (profile `<PROFILE>`, `<CLASSIFICATION>`), ветка `<BRANCH>` @ `<COMMIT>`
**Кластеры конфигов:** см. README плана

## Сводка

| Раздел | Всего | PASSED | FAILED | SKIPPED | N/A |
|---|---|---|---|---|---|
| Pre-flight (T) | 0 | 0 | 0 | 0 | 0 |
| Smoke (S) | 0 | 0 | 0 | 0 | 0 |
| Регрессия (R) | 0 | 0 | 0 | 0 | 0 |
| Acceptance (F) | 0 | 0 | 0 | 0 | 0 |
| Acceptance (I) | 0 | 0 | 0 | 0 | 0 |
| Cross-cutting (C) | 0 | 0 | 0 | 0 | 0 |
| **Итого** | **0** | 0 | 0 | 0 | 0 |

## Детали

### Pre-flight (T)
| ID | Status | Комментарий |
|---|---|---|
| <T1> | | |

### Smoke (S)
| ID | Cluster | Status | Комментарий |
|---|---|---|---|
| <S1> | <1> | | |

### Регрессия (R)
| ID | Tier | Status | Покрыто кейсом / коммит-фикс | Комментарий |
|---|---|---|---|---|
| <R1> | <A|B> | | | |

### Acceptance (<F>)
| ID | Tier | Cluster | Status | Комментарий |
|---|---|---|---|---|
| <F1> | <A|B> | <1> | | |

### Acceptance (<I>)
| ID | Tier | Cluster | Status | Комментарий |
|---|---|---|---|---|
| <I1> | <A|B> | <1> | | |

### Provider/variant matrix
| ID | Вариант | Сценарий | Status | Комментарий |
|---|---|---|---|---|
| <X-PM1> | | | | |

### Cross-cutting (C)
| ID | Status | Комментарий |
|---|---|---|
| <C1> | | |

## Найденные дефекты
| # | Описание | Repro | Severity | Issue / Commit |
|---|---|---|---|---|
| | | | | |

## Скриншоты
`reports/screenshots/<file>` — скриншоты критичных дефектов.

## Финальный вердикт
- [ ] Все T пройдены (или нерабочие инструменты зафиксированы)
- [ ] Unit-suite зелёный
- [ ] Все R пройдены
- [ ] F/I пройдены или явно SKIP с обоснованием
- [ ] Provider/variant matrices — минимум один вариант каждой строки
- [ ] C-кейсы без ошибок
- [ ] Return-to-defaults выполнен (`git status` чист)

**Решение:**
- [ ] ✅ Готов к MR в `<target-branch>`
- [ ] ⚠ Требуются доработки:
  - [ ] …
