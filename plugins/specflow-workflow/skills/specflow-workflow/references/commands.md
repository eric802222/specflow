# specflow CLI 速查

所有指令都接受 `--spec-root <path>`；不指定的話依序找
`SPECFLOW_SPEC_ROOT` 環境變數 → 目前目錄的 `.spec/` → 目前目錄本身。

```bash
# 建立 change
specflow init <change-id> <title> --type <feature|bugfix|hotfix|baseline> [--with-design]

# 對 proposal.md 執行 lint（吃 change-id 或路徑，不給參數就掛全部）
specflow lint [change-id-or-path]

# 算出下一步該做什麼（JSON 輸出，唯一該信任的規則來源）
specflow next <change-id>

# 套用一次合法的狀態轉移
specflow transition <change-id> <EVENT> [--auto-commit] [--commit-ref <sha>]

# 印出交付給 AI 的完整內容（純輸出，不落地成檔案）
specflow prompt <change-id> [--base <ref>]

# 純資訊：glossary.yaml 每個實體被檢查到哪幾層（不擋流程）
specflow coverage

# 把 specs/ 渲染成靜態 HTML（真的呼叫 dbml-renderer/tsp+Redoc/wireframe-lofi，
# 工具沒裝就退回顯示原始內容 + 安裝指令）
specflow render [--out dist]

# 除錯：印出目前解析到的 spec root
specflow root
```

## `transition` 的兩個 commit 相關旗標，容易搞混

- `--auto-commit`：轉移成功後**真的執行** `git add` + `git commit`，避免留下
  dirty 工作區
- `--commit-ref <sha>`：**純紀錄**，把這個 sha 寫進 `proposal.md` 的
  `implementation_commit` frontmatter 欄位，不做任何 git 操作——用來讓文件錖
  可以從 change 往回指到實際的實作 commit

兩者可以一起用，也可以只用其中一個，都是選填。

## 生命周期事件一覽（預設 `change-lifecycle.yaml`，可能被專案客製化）

| 事件 | 從 | 到 | 說明 |
|---|---|---|---|
| `LINT_PASS` | `draft`／`respec` | `delivered` | 自動（lint 通過即可建議） |
| `ISSUE_FOUND` | `delivered` | `respec` | 實作中發現規格要調整 |
| `DEV_DONE` | `delivered` | `ready` | 開發完成，等 review |
| `REVIEW_PASS` | `ready` | `merge_ready` | review 通過 |
| `REVIEW_REJECT` | `ready` | `respec` | review 發現規格問題 |
| `MERGED` | `merge_ready` | `applied` | 併入 main，流程終點 |
| `HOTFIX_LIVE` | `draft` | `live_pending_review` | 僅 `type: hotfix`，跳過事前審核 |
| `POSTREVIEW_DONE` | `live_pending_review` | `applied` | 補完事後審查 |
| `BASELINE_CAPTURED` | `draft` | `baseline_recorded` | 僅 `type: baseline`，直達終點 |

**這張表可能過期**——`<spec-root>/change-lifecycle.yaml` 存在的話，這個專案
用的是自己客製化的版本。永遠用 `specflow next` 的實際輸出確認，不要只信這張表。
