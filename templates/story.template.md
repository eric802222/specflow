---
name: "<簡短描述這組 story 的主題>"
type: story
status: draft
external_key: TICKET-XXX
refs:
  - "https://jira.example.com/browse/TICKET-XXX"
goal: <業務動機（why）——一句話，不描述怎麼做>
stories:
  - id: <snake_case_唯一識別>
    given: <角色與前提條件，不描述系統狀態>
    when: <一個觸發動作，不是一串流程>
    then: <對角色有意義的結果，不提實作細節>
    children:
      - id: <snake_case_唯一識別>.<child_id>
        given: <邊界條件的前提>
        when: <邊界情境的觸發>
        then: <邊界情境的結果>
---
