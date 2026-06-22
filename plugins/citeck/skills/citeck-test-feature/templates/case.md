# Cases: <SECTION> (<ID-RANGE>)

Дизайн/issue: <link to design doc or tracker issue>.

> ⚠ Общие правила для UI-кейсов — `references/playwright-tips.md`. Для HTTP-кейсов —
> `references/tools-cheatsheet.md` (gateway harness, async-polling, file upload).
> Все операции бьют по `<BASE_URL>`, мутации — только в `<TEST_WORKSPACE>`.

## <ID1>. <Краткое название кейса>
**Tier:** <A|B>  •  **Cluster:** <N>  •  **Tools:** `[HTTP]` `[RA]` `[LOG]`  •  **Subagent:** `<subagent-name>`
- **Шаги**: <что сделать — конкретные curl/Playwright/Records-операции>.
- **Acceptance**: <что должно произойти — HTTP-код/поле ответа, состояние в Records API, строка в логе>.
- **Note**: <опционально — особенности, зависимости от других кейсов, известные нюансы>.

## <ID2>. <Краткое название кейса>
**Tier:** <A|B>  •  **Cluster:** <N>  •  **Tools:** `[PW]`  •  **Subagent:** `<subagent-name>`
- **Шаги**: <...>.
- **Acceptance**: <...>.

<!-- Повторять блок на каждый кейс раздела. Шапка обязательна: Tier/Cluster/Tools/Subagent.
     ID сквозные в пределах буквы раздела (см. references/tier-cluster-model.md → ID-конвенции). -->
