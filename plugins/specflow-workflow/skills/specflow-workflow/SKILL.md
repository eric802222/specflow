---
description: 引導在 specflow 管理的專案裡工作——建立 change（proposal/design/tasks）、判斷該用哪種 type、走生命周期轉移、產生交付給 AI 的內容。使用時機：專案裡有 .spec/ 目錄或設了 SPECFLOW_SPEC_ROOT、使用者要求「開一個 change」「這個該用什麼 type」「這個 change 卡在哪」「幫我推進到下一步」，或需要建立/編輯 changes/<id>/ 底下的任何檔案時。
---

# specflow 工作流程

## 黃金規則：規則問工具，不要用猜的

specflow 的每個檔案（`proposal.md`／`tasks.md`／`design.md`／`review.md`）都有
對應的 linter 強制檢查格式，狀態轉移也有明確規則。**這些規則會變、會被
客製化**（`<spec-root>/change-lifecycle.yaml` 可以覆寫預設狀態機），永遠不要
憑記憶編規則，改用工具的實際輸出：

```bash
specflow next <change-id> --spec-root <spec-root>
```

這是唯一該信任的來源。它會回傳結構化 JSON，告訴你：現在合法的下一步是什麼
（`next_action`）、卡在哪裡（`blocking_errors`）、有沒有其他可選事件
（`other_events`／`available_events`）。**每次不確定該做什麼，先跑這個，
不要自己猜。**

## 開一個新 change：先決定 type

```bash
specflow init <change-id> <title> --type <feature|bugfix|hotfix|baseline> [--with-design]
```

決策依據（不是憑感覺選）：

| 情境 | type | 理由 |
|---|---|---|
| 要改變行為，範圍需要說清楚 Why/Goals/Non-Goals | `feature` | 唯一要求非目標區塊的 type |
| 修一個已經定義清楚的 bug | `bugfix` | 15 行上限，只要「壞在哪」「怎麼修」 |
| 生產環境正在出事，要先上線再補文件 | `hotfix` | 跳過事前審核，事後補驗屩報告（見下） |
| 描述既有系統現況，不是提議變更 | `baseline` | 沒有開發工作，直接進終點狀態 |

`feature`／`bugfix` 會自動產生 `tasks.md`；`baseline`／`hotfix` 不會（前者永遠
不需要，後者設計上是事後才補）。

**`--with-design`**：這個 change 有值得記錄的工程決策（取捨、備選方案考量）
就加這個旗標。`proposal.md` 的行數上限很緊（`bugfix` 只有 15 行），塞不下的
決策細節放 `design.md`——格式規則見 `references/design-format.md`，寫之前
**先讀那份參考**，不要憑印象套用格式，它有喳格的固定欄位規則。

## 決策/發現要記錄時：讀 design-format.md

`design.md`（工程決策）跟 `review.md`（code review 發現）共用同一套「固定
欄位 + checkbox 選項 + 摘要交叉比對」格式，規則細節、常見錯誤都在
`references/design-format.md`。這份格式的驗證很嚴格（不允許自由段落、待確認
項目要用 checkbox 選項不能假裝有答案），**寫之前一定要先讀那份參考**，寫完
用 `specflow next` 驗證（`gate_check` 會自動檢查這兩個檔案，存在就驗證）。

## 生命周期：正常流程長什麼樣

```
draft --(LINT_PASS)--> delivered --(DEV_DONE)--> ready
  --(REVIEW_PASS)--> merge_ready --(MERGED)--> applied
```

分支：

- `delivered` 階段發現規格要調整 → `ISSUE_FOUND` 打回 `respec`，改完 `LINT_PASS`
  再回 `delivered`
- `ready` 階段 review 沒過 → `REVIEW_REJECT` 打回 `respec`（不是打回 `ready`
  自己，記錄性小修正也走這條路）
- 緊急狀況（`type: hotfix`）→ `HOTFIX_LIVE` 跳過事前審核，先上線，進
  `live_pending_review`，補上 `tasks.md`（驗屩報告：症狀、根因、實際改了什麼）
  後才能 `POSTREVIEW_DONE` 到 `applied`
- `baseline` type → `BASELINE_CAPTURED` 直接到終點 `baseline_recorded`，不走
  上面這條完整流程

**不要背這張圖去猜下一步該打哪個事件**——這只是給你建立心智模型用的，實際
執行前一定要用 `specflow next` 確認這個專案現在真正合法的選項是什麼（可能被
客製化過）。

## 卡住的時候

`specflow next` 回傳 `next_action` 不是 `"transition"` 或 `"await_manual_signal"`
時，代表有東西擋住了（`fix_proposal_lint`／`write_tasks_md`／
`fix_design_lint`／`fix_review_lint`／`fix_change_shape` 等）。`blocking_errors`
陣列會列出具體哪裡不合規，**照著那個訊息精確修正，不要憑猜測大改**——這些
linter 的錯誤訊息設計成直接可執行。

## 產生交付內容

只有在 `specflow next` 顯示的狀態 `allows` 包含 `generate_delivery`（`delivered`／
`respec`／`ready`／`merge_ready`）才能產生：

```bash
specflow prompt <change-id> --spec-root <spec-root> [--base ref]
```

輸出是可以直接交給實作者/AI 的完整內容（proposal 摘要、`tasks.md`、Blast Radius
統計、`specs/` 的 git diff）。純輸出到 stdout，**不要把它寫成檔案**——寫進
`changes/<id>/` 會直接違反白名單。

## Code review 整合

MR/PR 的 review 討論要轉寫進 `review.md`，是另一個独立的 skill
（`mr-review-to-spec`，在 `specflow-review` plugin）——那個 skill 專門處理
「怎麼把 GitLab/GitHub 上的討論串轉成結構化格式」，這裡不重複。

## 常見錯誤（自我檢查）

- 直接手改 `changes/<id>/` 底下的檔案繞過 `specflow transition`——狀態欄位改了
  但沒有走過 `gate_check`，之後 `specflow next` 的判斷會跟實際情況兔不起來
- 猜狀態機規則而不是跑 `specflow next` 確認——這個專案可能有自己的
  `change-lifecycle.yaml` 覆寫版本
- 幫 `bugfix`／`hotfix` 套用 `feature` 的五段式模板（Why/Goals/Non-Goals）——
  範本跟規則都是依 `--type` 分開的，硬套會直接撞上行數上限
- 忘記 `design.md`／`review.md` 的固定欄位規則，寫成自由段落——寫之前先讀
  `references/design-format.md`
