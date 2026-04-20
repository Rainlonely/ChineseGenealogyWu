# 吴氏族谱后端架构与 API v1

## 1. 系统目标

本阶段后端采用 `FastAPI + SQLite`，围绕移动端原型中的五个核心页面提供正式 API：

1. 搜索首页
2. 查询结果页
3. 人物详情页
4. 支系展开页
5. 补充后代页

v1 的原则如下：

- 区分“古籍史料数字化”与“现代续修平台”两层语义
- 先完成只读查询能力，再提供“提交审核”能力
- 不做用户登录与身份校验
- 不允许匿名用户直接写入正式族谱数据

## 2. 数据分层

### Historical layer

沿用现有 SQLite 表：

- `groups`
- `pages`
- `persons`
- `relationships`
- `biography_pages`
- `person_biographies`

语义保持不变：

- `persons` 继续表达古籍人物与现有数字化成果
- `relationships` 继续表达当前历史父子链
- 不向历史层写入母系、夫妻、女儿等现代关系

### Modern layer

新增现代续修层：

- `modern_persons`
- `modern_relationships`
- `lineage_attachments`

职责：

- 记录现代续修人物
- 记录父女、母子、母女、夫妻等现代关系
- 把现代续修挂接到历史人物或现代人物上

### Submission layer

新增提交审核层：

- `change_submissions`

职责：

- 接收移动端提交的现代续修线索
- 进入 `pending` 队列
- 经内部接口审核后，再转入 modern layer

### Service view layer

服务层对前端统一输出：

- 搜索结果视图
- 人物详情视图
- 小传视图
- 路线缩略图视图
- 局部支系树视图

服务层负责把 historical layer 与 modern layer 合并成面向前端的 JSON，不把前端直接暴露给底层表结构。

## 3. 表设计草案

### `modern_persons`

- `id`
- `display_name`
- `gender`
- `birth_date`
- `death_date`
- `living_status`
- `surname`
- `is_external_surname`
- `education`
- `occupation`
- `bio`
- `created_from_submission_id`
- `status`
- `created_at`
- `updated_at`

### `modern_relationships`

- `id`
- `from_person_ref`
- `to_person_ref`
- `from_person_source`
- `to_person_source`
- `relation_type`
- `status`
- `created_from_submission_id`
- `created_at`
- `updated_at`

首批 `relation_type` 枚举：

- `father_son`
- `father_daughter`
- `mother_son`
- `mother_daughter`
- `spouse`

### `lineage_attachments`

- `id`
- `historical_person_ref`
- `modern_person_ref`
- `created_from_submission_id`
- `status`
- `created_at`

职责：

- 表达“现代续修从哪个历史人物继续往下写”
- 为搜索结果和人物详情提供“这一支已续修”的判断依据

### `change_submissions`

- `id`
- `target_person_ref`
- `target_person_source`
- `submission_type`
- `submitter_name`
- `submitter_contact`
- `payload_json`
- `status`
- `review_note`
- `created_at`
- `reviewed_at`

说明：

- v1 只实现 `change_submissions`
- 审核轨迹如果后续需要，再补 `submission_events`

## 4. API 草案

### 4.1 搜索

`GET /api/v1/search/persons?q=吴良佐&limit=20`

返回：

- `items[]`
  - `person_ref`
  - `person_source`
  - `name`
  - `father_name`
  - `generation_label`
  - `has_biography`
  - `has_modern_extension`
  - `summary_route`
  - `match_reason`

规则：

- v1 先做姓名精确/模糊匹配
- 同名人物全部列出
- 优先给出“父名 + 世代 + 是否有小传 + 是否已续修”

### 4.2 人物详情

`GET /api/v1/persons/{person_source}/{person_ref}`

返回：

- 基本信息
- 数据来源
- 父名 / 世代
- 是否有小传
- 是否存在现代续修支系
- 推荐动作

### 4.3 人物小传

`GET /api/v1/persons/{person_source}/{person_ref}/biography`

返回：

- `available`
- `source_type`
- `title`
- `text_raw`
- `text_linear`
- `text_punctuated`
- `text_baihua`

规则：

- 历史人物优先取 `person_biographies`
- 现代人物预留 `bio`

### 4.4 谱系路线缩略图

`GET /api/v1/persons/{person_source}/{person_ref}/route`

返回：

- `items[]`
  - `generation`
  - `name`
  - `person_ref`
  - `person_source`
  - `note`

规则：

- 历史人物优先走父系主链
- 已接入现代续修时，在尾部追加现代续修节点或说明
- 控制在首屏可读长度

### 4.5 局部支系树

`GET /api/v1/persons/{person_source}/{person_ref}/branch?up=2&down=3&include_daughters=1&include_spouses=1`

返回：

- `focus`
- `columns[]`
  - `label`
  - `generation`
  - `nodes[]`
    - `person_ref`
    - `person_source`
    - `name`
    - `relation_to_focus`
    - `node_type`
    - `relation_type`

规则：

- 只返回局部树
- 历史层默认只含父子链
- `include_daughters` 与 `include_spouses` 只影响 modern layer

### 4.6 续修提交

`POST /api/v1/submissions`

请求体：

- `target_person_ref`
- `target_person_source`
- `submitter_name`
- `submitter_contact`
- `new_person`
  - `birth_date`
  - `death_date`
  - `education`
  - `occupation`
- `relation`
- `notes`

行为：

- 只写入 `change_submissions`
- 返回 `submission_id` 和 `status=pending`

### 4.7 审核接口

- `GET /api/v1/admin/submissions`
- `POST /api/v1/admin/submissions/{submission_id}/approve`
- `POST /api/v1/admin/submissions/{submission_id}/reject`

规则：

- v1 不做正式鉴权，但路由独立
- `approve` 把提交转成 `modern_persons + modern_relationships + lineage_attachments`
- 审核操作必须幂等

## 5. 服务分层

目录结构：

```text
backend/
  app/
    api/
    db/
    repositories/
    schemas/
    services/
    main.py
    settings.py
```

约定：

- `api/`：HTTP 路由与参数校验
- `repositories/`：SQL 读写
- `services/`：历史层与现代层组合、路线摘要、树裁剪、审核转换
- `db/`：连接与现代层 schema 初始化

## 6. 实现顺序

1. 文档与骨架
2. 搜索、详情、小传、路线、局部树
3. 现代层建表
4. 提交与审核
5. 前端联调所需的字段统一与错误码补全
