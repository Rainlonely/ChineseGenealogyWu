# 族谱整理工作流与数据模型

## 当前工作流

当前已经形成稳定的三步工作流：

1. 单组整理  
   以 5 世代为一组处理，例如 `93-97`、`98-102`。  
   在组内完成 OCR 框绑定、页内补链、跨页补链，并持续消除“缺父”标记。

2. 单组合格  
   一组内除首世外，其余世代都没有“缺父”标记时，可视为这一组整理完成。

3. 组合并衔接  
   通过 bridge 文件把两组或多组运行时拼成合并工作区，只处理相邻组之间的跨组父子链，例如 `97 -> 98`、`10 -> 11`。

当前文件分层：

- 组内原始整理数据：`gen_093_097/group_template.json`、`gen_098_102/group_template.json`
- 跨组合并关系：`bridges/gen_093_097__gen_098_102.json`、`bridges/gen_001_005__gen_006_010.json` 等
- 运行时合并视图：由 review server 动态拼出，不直接作为长期主存储

## 当前主存策略

当前已经调整为：

- `JSON / bridge JSON` 仍然是人工编辑时的工作底稿
- `SQLite` 不再只是少数组的演示镜像，而是每次保存后自动同步整套工作区

也就是说：

- 单组保存：写回对应 `group_template.json`
- 合并保存：写回对应 bridge JSON
- 同时服务端会自动扫描全部 `gen_*` 与全部 `bridges/*.json`，重建完整 SQLite

因此数据库里会持续累积出当前最新的 `1-102世` 已整理结构，不需要再额外维护一份“总 JSON”。

## 收敛后的数据库建模

本阶段采用“收敛方案”：

- `person` 是核心实体
- 不单独引入 `person_occurrences`
- 人物在书中的主位置直接存在 `persons` 表中
- 子数量、子 id 不作为主存字段，而是通过关系表统计

这样更贴合当前真实业务，也更容易从现有 JSON 平滑迁移。

## 表设计

### `groups`

表示一个整理批次，例如 `gen_093_097`、`gen_098_102`。

关键字段：

- `id`
- `label`
- `page_start`
- `page_end`
- `source_pdf`
- `raw_images_dir`
- `cropped_images_dir`
- `notes_json`
- `status`

### `pages`

表示组内的单页信息。整页图片不存二进制，只存路径。

关键字段：

- `group_id`
- `page_no`
- `image_path`
- `generation_hint_json`
- `text_items_json`
- `line_items_json`
- `raw_markers_json`
- `manual_notes_json`
- `people_locked`
- `page_role`
- `keep_generation_axis`

### `persons`

表示人物本体，以及当前主位置。

关键字段：

- `id`
- `group_id`
- `name`
- `canonical_name`
- `generation`
- `root_order`
- `primary_page_no`
- `primary_page_image_path`
- `bbox_json`
- `poly_json`
- `glyph_asset_path`
- `aliases_json`
- `notes_json`
- `is_verified`
- `verified_at`
- `review_status`
- `remark`

说明：

- `glyph_asset_path` 指向落地的小截图文件，不再把 base64 长串继续塞在 JSON/数据库里
- `primary_page_image_path` 只存整页路径，不把整页图二进制写入数据库

### `relationships`

表示父子边。  
组内边与跨组边统一建模，通过 `scope` 和 `scope_ref` 区分来源。

关键字段：

- `scope`
  - `group_internal`
  - `group_bridge`
- `scope_ref`
  - 例如 `gen_093_097`
  - 或 `merge__gen_001_005__gen_006_010`
- `parent_person_id`
- `child_person_id`
- `relation_type`
- `birth_order_under_parent`
- `confidence`
- `page_sources_json`
- `notes_json`
- `is_verified`
- `verified_at`
- `remark`

## 派生数据

以下内容不建议作为主存字段：

- `child_count`
- `child_ids`

原因：

- 它们本质上是 `relationships` 的派生结果
- 一旦补链、改链、删链，直接存数组会增加维护成本

因此 schema 中提供了两个视图：

- `v_person_child_stats`
- `v_person_children_json`

分别用于统计子数量和生成子 id 列表。

另外，为了支持“完整树”查询，还提供了：

- `v_person_parent_links`
  用于统计一个人物当前已拥有的组内父链 / 跨组父链数量
- `v_person_tree_status`
  用于给人物打上：
  - `isolated`
  - `linked_inside_group`
  - `linked_cross_group`
  - `verified`
- `v_group_completion`
  用于统计每组当前还缺多少父链，以及有多少人物已经完成跨组衔接

## 为什么不拆 `person_occurrences`

当前项目阶段，一个人物基本只对应书上的一个主位置。  
如果现在就拆 `occurrence` 表，会增加迁移复杂度，但业务收益不大。

因此当前采用更简化的收敛模型：

- 一个人物只保留一个主位置
- 以后如果确实出现“同一人物多个有效位置”的业务，再从 `persons` 中拆出去

## 迁移脚本

已提供迁移脚本：

- [scripts/import_genealogy_to_sqlite.py](/Users/rainwu/Projects/FamilyGenealogyBook/scripts/import_genealogy_to_sqlite.py)

当前 review server 已接入 SQLite 全量同步：

- 前端保存仍然只写 JSON / bridge
- 每次保存完成后，服务端会自动扫描并重建一次 SQLite
- 扫描范围包括：
  - 全部 `gen_*/group_template.json`
  - 全部 `bridges/*.json`
- 因此前端编辑流不变，但数据库会持续保持当前全工作区最新状态

同时会把人物 `glyph_image` 中的 data URL 解码落地到：

- `data/glyph_assets/`

并把路径写入 `persons.glyph_asset_path`。

## 初始化方式

```bash
python3 scripts/import_genealogy_to_sqlite.py --reset
```

默认数据库输出：

- `data/genealogy.sqlite`

Schema 文件：

- [db/schema.sql](/Users/rainwu/Projects/FamilyGenealogyBook/db/schema.sql)

## 查询脚本

已提供 SQLite 查询脚本：

- [scripts/query_genealogy_sqlite.py](/Users/rainwu/Projects/FamilyGenealogyBook/scripts/query_genealogy_sqlite.py)

示例：

```bash
python3 scripts/query_genealogy_sqlite.py person --name 梅
python3 scripts/query_genealogy_sqlite.py person --id p_47_003
python3 scripts/query_genealogy_sqlite.py page --group gen_098_102 --page 47
python3 scripts/query_genealogy_sqlite.py bridges
python3 scripts/query_genealogy_sqlite.py missing --group gen_093_097
python3 scripts/query_genealogy_sqlite.py completion
python3 scripts/query_genealogy_sqlite.py completion --group gen_091_095
python3 scripts/query_genealogy_sqlite.py tree-status --group gen_098_102 --generation 98
```
