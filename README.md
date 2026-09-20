# specflow

Everything-as-Code 全端規格編譯與 AI 交付管線工具。

## 核心痛點

- **溝通與審核斷層**：Live 原型難維護、傳統 PRD 充斥廢話，交接靠人腦記憶造成規格漂移（Drift）。
- **評估與交付斷層**：需求變更時影響範圍（Blast Radius）無法精確預估，自然語言 Prompt 容易讓 AI 產生幻覺或破壞既有架構。

## 設計哲學

1. **Everything-as-Code (SSOT)**：架構、契約與邏輯全面代碼化、版本控管化。
2. **規格即骨架（Spec-Executable）**：DSL 必須可 Lint、可編譯出產物、可當測試斷言。
3. **提案槽位限縮（Slot-Filling Schema）**：Proposal 用 Frontmatter Markdown，Linter 硬性限制行數與結構。
4. **差量交付（Diff-Driven AI Delivery）**：規格異動發生在對應的 change branch 上，MR 的 diff 即交付給 AI 的 Prompt。
5. **人跟 AI 走同一條窄路**：每種文件都有硬性結構上限、白名單擋住多餘檔案、下一步永遠由工具算出來（`specflow next`），不是靠 AI 自由判斷。

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
# 在目標專案的 .spec/changes/ 底下建立一個 change
specflow init CP-153-discount-reason "換貨折扣申請新增理由欄位"

# 對所有 change 的 proposal.md 執行 lint（預設: <spec-root>/changes/*/proposal.md）
specflow lint

# 算出這個 change 下一步該做什麼（結構化 JSON，人跟 AI 都讀同一份契約）
specflow next CP-153-discount-reason

# 套用一次合法的狀態轉移
specflow transition CP-153-discount-reason LINT_PASS
```

## change 生命週期（`templates/change-lifecycle.yaml`）

```
draft --(LINT_PASS, 自動)--> delivered --(ISSUE_FOUND, 人工)--> respec --(LINT_PASS)--> delivered
                                        --(DEV_DONE, 人工)-----> ready --(MERGED, 人工)--> applied
```

`specflow next` 讀這張狀態機 + 跑對應 linter，回傳「下一步合法動作是什麼、被什麼錯誤擋住」；
`specflow transition` 套用一次轉移，`auto` 轉移在套用前會重新驗證一次 lint，避免繞過 `next`
直接跳過檢查。

## Proposal 規則（`lib/linters/proposal_lint.py`）

1. Frontmatter 必須包含 `id`, `title`, `impact_surface`。
2. 正文有效非空行數不得超過 35 行。
3. 嚴禁出現代碼塊標記（```` ``` ````）。
4. 必須存在 `## 3. 非目標 (Non-Goals)` 區塊。

## tasks.md 規則（`lib/linters/task_lint.py`）

每行必須是 `- [ ] <task-id>: <一句話描述> (touches: <file1>, <file2>)`，`task-id` 只能是
kebab-case、不允許巢狀子項目、禁代碼塊、task 數量上限 15 個（超過代表這個 change 該拆了）。

## change 資料夾白名單（`lib/linters/change_shape_lint.py`）

`changes/<id>/` 底下只允許 `proposal.md`、`tasks.md` 兩個檔案存在，出現任何第三個檔案
（不管內容多好，包含 AI 自己覺得有幫助而多寫的說明文件）一律判定失敗。

## 跨規格一致性檢查（`lib/linters/cross_spec_lint.py`）

驗證 `db/schema.dbml`、`api/main.tsp`、`ui/**/*.wf.yaml`、`logic/` 四層裡引用的列舉值，
是否都跟 `glossary.yaml` 的定義一致。命名慣例：DBML enum 用 `<entity_key>_status`，
TypeSpec enum 用 `PascalCase(entity_key) + "Status"`。找不到對應來源時該層「略過」，
但抓到的值不合法一律報錯。

## 目錄結構（specflow 工具自己）

```
specflow/
├── bin/specflow.py              CLI 入口（init / lint / next / transition / root）
├── pyproject.toml                pip install -e . 的 packaging 設定
├── templates/                    規格範本
│   ├── proposal.template.md
│   ├── tasks.template.md
│   ├── glossary.template.yaml
│   ├── rules.template.yaml
│   └── change-lifecycle.yaml     change 自己的狀態機定義
├── lib/
│   ├── linters/
│   │   ├── proposal_lint.py      Proposal 格式檢查
│   │   ├── task_lint.py          tasks.md 結構檢查
│   │   ├── change_shape_lint.py  change 資料夾白名單
│   │   └── cross_spec_lint.py    跨規格一致性檢查（db/api/ui/logic ↔ glossary）
│   ├── analyzers/diff_analyzer.py   影響範圍（Blast Radius）統計
│   ├── generators/prompt_gen.py     Diff 即 Prompt 生成器
│   └── workflow/
│       ├── lifecycle.py          解析 change-lifecycle.yaml
│       └── next_action.py        算出「下一步該做什麼」的結構化契約
└── tests/                        單元測試（41 個，涵蓋全部 linter + CLI 路徑解析 + 端到端生命週期）
```

## 現況與待補

**已完成**：proposal/tasks 範本、四種 linter（proposal/task/change_shape/cross_spec）、
change 生命週期狀態機、`specflow` CLI（可獨立安裝、跟目標 repo 解耦，支援 monorepo 與獨立
spec repo 兩種模式）、單元測試。

**待補**：
- `diff_analyzer`／`prompt_gen` 尚未接進 CLI 子命令，也還沒整合 `next_action` 的狀態資訊。
- `cross_spec_lint` 的命名慣例是寫死的，不符合的專案會被判定「略過」而非報錯，之後可以加
  一份可選的 `.spec/cross_spec_map.yaml` 讓專案明確宣告對照關係。
- CI 範例（pre-commit / MR pipeline 呼叫 `specflow lint` + `cross_spec_lint`）還沒寫。
