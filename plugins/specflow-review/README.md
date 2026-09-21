# specflow-review

Claude Code plugin：把 GitLab/GitHub MR 或 PR 的 code review 討論串，轉寫成
[specflow](https://github.com/eric802222/specflow) 的 `review.md` 格式（固定
欄位、checkbox 選項、摘要交叉比對），並用 `review_lint` 驗證格式。

## 為什麼需要這個

specflow 本身是純本機檔案系統工具，完全不碰 GitLab/GitHub API——這個 plugin
是橋接層：怎麼把 MR 上的討論轉寫成規格檔案，需要一個能存取那些平台的 agent
去做，而不同團隊用的平台、connector 都不一樣，所以刻意做成獨立的 skill，
不綁死在 specflow 核心裡。

## 安裝

```bash
claude --plugin-dir ./plugins/specflow-review
```

或加進 marketplace 後：

```
/plugin install specflow-review@<your-marketplace>
```

## 用法

在有 specflow change 的專案裡，直接跟 Claude 說：

> 把這個 MR 的 review 整理進 CP-1055 的 spec

Skill 會自動被觸發（`disable-model-invocation` 未設定，屬於 model-invoked），
讀取 MR 討論、轉寫成 `changes/CP-1055/review.md`，並提示你跑 `specflow next`
驗證格式。

## 需要什麼

- 一個已經在跑 specflow 的專案（`.spec/changes/<id>/` 存在）
- 存取 MR/PR 資料的方式：GitLab/GitHub connector，或直接把 MR 頁面內容貼給
  Claude
