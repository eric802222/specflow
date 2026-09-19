# specflow

Everything-as-Code 全端規格編譯與 AI 交付管線工具。

## 核心痛點

- **溝通與審核斷層**：Live 原型難維護、傳統 PRD 充斥廢話，交接靠人腦記憶造成規格漂移（Drift）。
- **評估與交付斷層**：需求變更時影響範圍（Blast Radius）無法精確預估，自然語言 Prompt 容易讓 AI 產生幻覺或破壞既有架構。

## 設計哲學

1. **Everything-as-Code (SSOT)**：架構、契約與邏輯全面代碼化、版本控管化。
2. **規格即骨架（Spec-Executable）**：DSL 必須可 Lint、可編譯出產物、可當測試斷言。
3. **提案槽位限縮（Slot-Filling Schema）**：Proposal 用 Frontmatter Markdown，Linter 硬性限制行數與結構。
4. **差量交付（Diff-Driven AI Delivery）**：修改只發生在 `.spec/`，Git Diff 即交付給 AI 的 Prompt。

## `.spec/` 目錄約定

| 用途 | 路徑 | 格式 |
| --- | --- | --- |
| 提案入口 | `proposals/*.md` | Frontmatter Markdown |
| 領域詞彙 | `glossary.yaml` | YAML |
| 資料庫 | `db/schema.dbml` | DBML |
| API 契約 | `api/main.tsp` | TypeSpec |
| 介面與動線 | `ui/pages/*.wf.yaml` | [wireframe-lofi](https://github.com/eric802222/wireframe-lofi) |
| 業務決策 | `logic/rules/*.yaml` | DMN 2D 決策表 |
| 狀態機 | `logic/lifecycle.yaml` | XState/SCXML |

## 安裝

```
pip install -r requirements.txt
```

## 快速開始

```
# 建立一份填空用 Proposal（會寫到 ./proposals/）
python3 bin/specflow.py init "報價單允許批次核准"

# 對 proposals/*.md 執行 lint（也可指定路徑）
python3 bin/specflow.py lint
```

## Proposal 規則（`lib/linters/proposal_lint.py`）

1. Frontmatter 必須包含 `id`, `title`, `impact_surface`。
2. 正文有效非空行數不得超過 35 行。
3. 嚴禁出現代碼塊標記（```` ``` ````）。
4. 必須存在 `## 3. 非目標 (Non-Goals)` 區塊。

## 目錄結構

```
specflow/
├── bin/specflow.py              CLI 入口（init / lint）
├── templates/                   規格範本（proposal / glossary / rules）
├── lib/
│   ├── linters/
│   │   ├── proposal_lint.py     第一道防線：Proposal 格式檢查
│   │   └── cross_spec_lint.py   跨規格一致性檢查（status ↔ glossary）
│   ├── analyzers/diff_analyzer.py   影響範圍（Blast Radius）統計
│   └── generators/prompt_gen.py     Diff 即 Prompt 生成器
├── tests/                        單元測試
└── proposals/                    存放實際提案（.gitkeep 佔位）
```

## 現況與待補

**已完成（MVP 第一道防線）**：proposal 範本、`proposal_lint`、CLI `init`/`lint`、單元測試。

**待補**：
- `cross_spec_lint` 目前只涵蓋 `logic/` 對 `glossary.yaml` 的 status 檢查，尚未涵蓋 `db/schema.dbml`、`api/main.tsp`、`ui/pages/*.wf.yaml` 的枚舉對照。
- `diff_analyzer` 目前只做「按目錄分類計數」，尚未做跨檔案引用追蹤。
- `prompt_gen` 尚未整合 `diff_analyzer` 的統計結果到 Prompt 摘要中。
