# 族谱姓名检索与用户勘误 v1

## Summary

这一版解决两个直接影响对外使用的问题：

1. 用户输入的姓名不一定和库里的主名完全一致
2. 历史人物姓名存在 OCR 和人工校对误差，需要用户提交勘误并进入审核

v1 采用两层机制：

- `主展示名 + 搜索别名`
- `用户勘误提交 + 后台审核处理`

不直接改动历史层建模语义，不在前台开放直接编辑。

## 数据设计

### 1. 人物搜索别名

新增表 `person_search_aliases`：

- `id`
- `person_ref`
- `person_source` (`historical` / `modern`)
- `alias_text`
- `alias_type`  
  首批取值：`manual_alias` `correction_accepted` `ocr_variant` `simplified_variant` `traditional_variant`
- `status` (`active` / `inactive`)
- `source_submission_id`
- `created_at`

用途：

- 不改变人物主展示名
- 给搜索提供额外命中入口
- 审核通过的勘误可先作为 alias 生效

### 2. 用户勘误提交

新增表 `correction_submissions`：

- `id`
- `target_person_ref`
- `target_person_source`
- `field_name`  
  v1 固定为 `name`
- `current_value`
- `proposed_value`
- `submitter_name`
- `submitter_contact`
- `reason`
- `evidence_note`
- `status` (`pending` / `approved` / `rejected`)
- `resolution_type` (`apply_as_primary` / `apply_as_alias`)
- `review_note`
- `created_at`
- `reviewed_at`

## 搜索规则

搜索不再只查主名，而是同时查：

- 历史人物：`persons.name`、`persons.canonical_name`、`person_search_aliases.alias_text`
- 现代人物：`modern_persons.display_name`、`person_search_aliases.alias_text`

命中优先级：

1. `primary_exact`
2. `alias_exact`
3. `primary_fuzzy`
4. `alias_fuzzy`

接口返回补充：

- `matched_name`
- `match_type`

前端可据此提示“按别名命中”。

## API

### 搜索增强

`GET /api/v1/search/persons?q=吴永昌&limit=20`

返回新增：

- `matched_name`
- `match_type`

### 用户勘误提交

`POST /api/v1/corrections`

请求体：

- `target_person_ref`
- `target_person_source`
- `submitter_name`
- `submitter_contact`
- `field_name` (`name`)
- `current_value`
- `proposed_value`
- `reason`
- `evidence_note`

行为：

- 只进入 `correction_submissions`
- 默认 `status = pending`

### 后台审核

- `GET /api/v1/admin/corrections`
- `POST /api/v1/admin/corrections/{correction_id}/approve`
- `POST /api/v1/admin/corrections/{correction_id}/reject`

审核通过的两种处理：

- `apply_as_primary`  
  更新正式姓名，并把旧值写入 alias
- `apply_as_alias`  
  不改正式姓名，只把建议值写入 alias

## Phase 1 Scope

本阶段只实现：

- alias 数据表
- 搜索接口接入 alias
- 姓名纠错提交接口
- 后台审核接口
- 审核通过后写入 alias / 正式姓名

暂不实现：

- 拼音搜索
- 音近字自动规则
- 图像附件上传
- 更复杂的人物字段纠错
