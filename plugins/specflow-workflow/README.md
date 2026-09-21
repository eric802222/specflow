# specflow-workflow

Claude Code plugin：教 Claude 完整的 [specflow](https://github.com/eric802222/specflow)
工作流程——建立 change、判斷該用哪種 type、走生命周期轉移、產生交付內容。

## 設計原則：規則問工具，不要背下來

這個 skill 刻意不把 specflow 的所有規則死記在 prompt 裡——規則會變、會被
`change-lifecycle.yaml` 客製化。skill 教的是**方法**（先跑 `specflow next`
確認合法選項，照著 `blocking_errors` 精確修正），細節格式規則（`design.md`／
`review.md` 的固定欄位）放在 `references/`，用漸進式揭露：需要寫這類檔案時
才讀那份參考，不會把不相關的細節塞滿 context。

## 安裝

```bash
claude --plugin-dir ./plugins/specflow-workflow
```

## 搭配使用

- `specflow-review`（同一個 repo 底下的另一個 plugin）：把 MR/PR review 討論
  轉寫成 `review.md`。這兩個 plugin 是同一套工具鎈的不同切面，建議一起裝，
  但各自独立、互不依賴。

## 內容

```
skills/specflow-workflow/
├── SKILL.md                        主流程：type 決策、生命周期、卡住怎麼辦
└── references/
    ├── design-format.md            design.md／review.md 固定欄位格式細節
    └── commands.md                 CLI 指令速查、生命周期事件表
```
