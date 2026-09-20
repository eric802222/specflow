# specflow

Everything-as-Code 全端規格編譯與 AI 交付管線工具。

## 核心痛點

- **溝通與審核斷層**：Live 原型難維護、傳統 PRD 充斥廢話，交接靠人腦記憶造成規格漂移（Drift）。
- **評估與交付斷層**：需求變更時影響範圍（Blast Radius）無法精確預估，自然語言 Prompt 容易讓 AI 產生幻覺或破壞既有架構。

## 設計哲學

1. **Everything-as-Code (SSOT)**：架構、契約與邏輯全面代碼化、版本控管化。
2. **規格即骨架（Spec-Executable）**：DSL 必須可 Lint、可編譯出產物、可當測試斷言。
3. **提案槽位限縮（Slot-Filling Schema）**：Proposal 用 Frontmatter Markdown，Linter 依 `type`（feature/bugfix/hotfix）套用不同的結構限制，不逼小改動硬套大範本。
4. **差量交付（Diff-Driven AI Delivery）**：規格異動發生在對應的 change branch 上，`specflow prompt` 直接把 diff 組成交付內容，不另外維護交付文件。
5. **人跟 AI 走同一條窄路**：每種文件都有硬性結構上限、白名單擋住多餘檔案、下一步永遠由工具算出來（`specflow next`），不是靠 AI 自由判斷。
6. **正常流程之外要有正當的快速通道**：緊急變更（hotfix）如果沒有工具支援的快速路徑，人只會繞過工具直接改——`specflow` 提供仿 ITIL Emergency Change 的 `HOTFIX_LIVE` 事件，換速度但強制事後補審查。

## `.spec/` 目錄約定（目標專案裡的樣子）

```
.spec/
├── specs/                    ← SSOT，目前正式生效的規格
│   ├── glossary.yaml
│   ├── db/schema.dbml
│   ├── api/main.tsp
│   ├── ui/pages/*.wf.yaml    （wireframe-lofi 語法）
│   └── logic/rules/*.yaml
└── changes/
    ├── <change-id>/           ← 只放 proposal.md、tasks.md（change_shape_lint 白名單強制）
    │   ├── proposal.md
    │   └── tasks.md
    └── archive/
        └── <change-id>/       ← merge 後封存
```

規格異動直接發生在對應 branch 的 `specs/` 上，`changes/<id>/` 只放流程文件（Why/Goals/
Non-Goals + task 清單），不放規格副本——隔離靠 git branch/MR 本身，不是靠工具另外模擬一套
沙盒。`change-id` 建議用 `<JIRA-KEY>-<slug>` 的格式，跟 Jira 單天生對得上。

## 安裝

作為獨立指令安裝（推薦，裝好後 `specflow` 到處都能呼叫，不需要跟目標專案在同一個 repo）：

```
pip install -e .
```

只是想跑這個 repo 自己的測試、不想裝成指令：

```
pip install -r requirements.txt
```

## `--spec-root`：指向任何一個目標專案

specflow 本身（這支 CLI、範本、linter 規則、狀態機定義）跟它管理的「目標專案」是分開的。
目標專案的 spec root 可以在任何 repo 裡，解析順序：

1. `--spec-root <path>` 明確指定
2. 環境變數 `SPECFLOW_SPEC_ROOT`
3. 目前目錄底下的 `.spec/`（規格嵌在應用程式 repo 裡的 monorepo 模式）
4. 目前目錄本身（規格自己獨立一個 repo，repo root 就是 spec root——不用另外建 `.spec/` 包一層）

```
specflow root --spec-root /path/to/some-project/.spec   # 除錯用，印出目前解析到的位置
```

## 快速開始

```
# 在目標專案的 .spec/changes/ 底下建立一個 change（預設 type: feature）
specflow init CP-153-discount-reason "換貨折扣申請新增理由欄位"

# 對所有 change 的 proposal.md 執行 lint（預設: <spec-root>/changes/*/proposal.md）
specflow lint

# 算出這個 change 下一步該做什麼（結構化 JSON，人跟 AI 都讀同一份契約）
specflow next CP-153-discount-reason

# 套用一次合法的狀態轉移
specflow transition CP-153-discount-reason LINT_PASS

# 開發階段：給一個 change-id，直接印出交付給 AI 的完整內容（純輸出，不落地成檔案）
specflow prompt CP-153-discount-reason --base main
```

## change 生命週期（`templates/change-lifecycle.yaml`）

```
draft --(LINT_PASS, 自動)--> delivered --(ISSUE_FOUND, 人工)--> respec --(LINT_PASS)--> delivered
                                        --(DEV_DONE, 人工)-----> ready --(MERGED, 人工)--> applied

draft --(HOTFIX_LIVE, 人工, 僅 type: hotfix)--> live_pending_review --(POSTREVIEW_DONE, 人工)--> applied
```

`specflow next` 讀這張狀態機 + 跑對應 linter，回傳「下一步合法動作是什麼、被什麼錯誤擋住」；
`specflow transition` 套用一次轉移——**不管 auto 還是手動事件，都會先整組跑一次 gate_check**，
不能只挑 auto 事件才重驗（這是修過的真實漏洞：手動事件曾經完全沒被驗證，等於 `next` 擋得住
的東西，直接呼叫 `transition` 卻能全部繞過去）。`<spec-root>/change-lifecycle.yaml` 存在的話
會優先採用，讓不同專案客製化自己的流程。

有自動轉移可用時，`specflow next` 不會把其他合法的手動事件藏起來——回應裡的 `other_events`
會列出同時存在的其他選項（例如 hotfix 類型的 change 在 `draft` 狀態，除了看到 `LINT_PASS`
的建議，也會在 `other_events` 看到 `HOTFIX_LIVE`），不然緊急通道做了也沒人知道在哪。

## Hotfix：正當的緊急通道

```
specflow init CP-999 "資料庫連線池爆掉" --type hotfix
specflow transition CP-999 HOTFIX_LIVE        # 跳過正常審核，直接記錄「已上線」
# ...補上 tasks.md（事後審查用的驗屍報告：症狀、根因、實際改了哪裡）...
specflow transition CP-999 POSTREVIEW_DONE    # 事後審查補交，流程才真正結束
```

仿 ITIL 的 Emergency Change：**跳過事前審核換取速度，但事後一定要補一份記錄**，不會因為
「火滅了」就不了了之——`live_pending_review` 狀態要求 `tasks.md` 存在，`specflow next` 會
一直提醒這個 change 還欠一份事後審查，直到補上為止。`HOTFIX_LIVE` 只有 `type: hotfix` 的
change 才能觸發（`requires_type` 機制），`type: feature` 的 change 想用會被直接拒絕——這條
界線需要誠實標記，specflow 沒辦法阻止有人謊報 type 抄捷徑，那件事的防線還是回到 MR review。

`specflow init --type` 支援三種：`feature`（預設，35 行上限 + 必須有非目標區塊）、`bugfix`
（15 行上限，只要「壞在哪」「怎麼修」）、`hotfix`（10 行上限，只要「症狀」「根因」）——範圍
明確的小改動不該被逼著套用新功能才需要的五段式模板。

## `specflow prompt`：給 change-id，換交付內容

```
specflow prompt <change-id> [--base main]
```

跑 gate_check 確認這個 change 合法之後，組出一份完整內容印到 stdout：Proposal 的 Why/Goals
摘要、Blast Radius 統計、`specs/` 相對於 `--base` 分支的完整 git diff、交付要求。**刻意不寫
成任何新檔案**——寫進 `changes/<id>/` 會直接被 `change_shape_lint` 的白名單擋下（那條線是
刻意畫的：change 資料夾只能有 `proposal.md`、`tasks.md`）。RD 自己複製貼上或接到別的工具。

## Proposal 規則（`lib/linters/proposal_lint.py`）

依 frontmatter 的 `type` 欄位套用不同規則：

| type | 正文行數上限 | 必要區塊 |
| --- | --- | --- |
| feature（預設） | 35 | `## 3. 非目標 (Non-Goals)` |
| bugfix | 15 | 無強制區塊 |
| hotfix | 10 | 無強制區塊 |

不管哪種 type，frontmatter 都必須包含 `id`, `title`, `impact_surface`，且全文嚴禁代碼塊
標記（```` ``` ````）。

## tasks.md 規則（`lib/linters/task_lint.py`）

每行必須是 `- [ ] <task-id>: <一句話描述> (touches: <file1>, <file2>)`，`task-id` 只能是
kebab-case、不允許巢狀子項目、禁代碼塊、task 數量上限 15 個（超過代表這個 change 該拆了）。

## change 資料夾白名單（`lib/linters/change_shape_lint.py`）

`changes/<id>/` 底下只允許 `proposal.md`、`tasks.md` 兩個檔案，加上 `.gitkeep`（唯一放行的
點開頭檔案）。出現任何第三個檔案或任何隱藏子目錄，一律判定失敗——不審查內容，只審查資格。

## 跨規格一致性檢查（`lib/linters/cross_spec_lint.py`）

驗證 `db/schema.dbml`、`api/main.tsp`、`ui/**/*.wf.yaml`、`logic/` 四層裡引用的列舉值，
是否都跟 `glossary.yaml` 的定義一致。命名慣例：DBML enum 用 `<entity_key>_status`，
TypeSpec enum 用 `PascalCase(entity_key) + "Status"`。找不到對應來源時該層「略過」，
但抓到的值不合法一律報錯。

## 目錄結構（specflow 工具自己）

```
specflow/
├── bin/specflow.py              CLI 入口（init / lint / next / transition / prompt / root）
├── pyproject.toml                pip install -e . 的 packaging 設定
├── templates/                    規格範本
│   ├── proposal.template.md      type: feature
│   ├── proposal-bugfix.template.md   type: bugfix
│   ├── proposal-hotfix.template.md   type: hotfix
│   ├── tasks.template.md
│   ├── glossary.template.yaml
│   ├── rules.template.yaml
│   └── change-lifecycle.yaml     change 自己的狀態機定義（含 hotfix 分支）
├── lib/
│   ├── common/
│   │   ├── frontmatter.py        共用的 frontmatter 解析/寫入（單行替換，不重新序列化整份）
│   │   └── atomic_write.py       原子寫入（暫存檔 + os.replace()）
│   ├── linters/
│   │   ├── proposal_lint.py      Proposal 格式檢查（依 type 調整規則）
│   │   ├── task_lint.py          tasks.md 結構檢查
│   │   ├── change_shape_lint.py  change 資料夾白名單
│   │   └── cross_spec_lint.py    跨規格一致性檢查（db/api/ui/logic ↔ glossary）
│   ├── analyzers/diff_analyzer.py   影響範圍（Blast Radius）統計
│   ├── generators/prompt_gen.py     給 change-id 組出交付 Prompt
│   └── workflow/
│       ├── lifecycle.py          解析 change-lifecycle.yaml（含 requires_type 篩選）
│       └── next_action.py        gate_check + 算出「下一步該做什麼」
└── tests/                        單元測試（86 個，涵蓋全部 linter + CLI 路徑解析 + 端到端生命週期 + hotfix 流程）
```

## 現況與待補

**已完成**：proposal/tasks 範本（依 type 分三種）、四種 linter（proposal/task/change_shape/
cross_spec）、change 生命週期狀態機（`gate_check` 統一把關，next/transition/prompt 共用同一
份檢查邏輯；含 hotfix 緊急通道）、`specflow` CLI（可獨立安裝、跟目標 repo 解耦，支援
monorepo 與獨立 spec repo 兩種模式）、`specflow prompt` 給 change-id 直接換交付內容（不落地
成檔案）、原子寫入、單元測試。

**待補**：
- `cross_spec_lint` 的命名慣例是寫死的，不符合的專案會被判定「略過」而非報錯，之後可以加
  一份可選的 `.spec/cross_spec_map.yaml` 讓專案明確宣告對照關係。
- `proposal.md` 跟 `tasks.md` 沒有語意層面的一致性檢查（例如 task 的 `touches` 是否仍落在
  `impact_surface` 宣告範圍內）——這是 spec-kit 自己也還沒解決的「衍生文件跟權威文件漂移」
  問題，需要另開一輪設計討論。
- 半途而廢卡在 `respec`/`live_pending_review` 的殭屍 change 沒有代謝機制（TTL、提醒）。
- Rollback 沒有工具支援——要撤銷一個已 `applied` 的變更，得手動開一個新 change 去逆轉它。
- CI 範例（pre-commit / MR pipeline 呼叫 `specflow lint` + `cross_spec_lint`）還沒寫。
