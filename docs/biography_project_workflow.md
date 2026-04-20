# 人物小传项目说明

## 目标

把前编中的人物小传，从原始古籍页逐页整理成可校对、可关联、可入库的数据。

当前范围：

- PDF：`1前编-68页.pdf`
- 页码：`29-67`
- 对应人物：前 `1-92世`

## 项目模式

沿用挂线图项目的基本节奏，但把识别对象改成“人物标题 + 传记正文”：

1. 逐页识别
2. 人工校对和人物关联
3. 结构化整理并入库

## 页内读取规则

- 页面从右到左分人物栏位。
- 每个人物栏位内，再按从右到左读取正文列。
- 单列内部按从上到下读取。
- 先确认“哪些列属于哪个人物”，再做正文拼接。

## 数据落点

SQLite 新增两层：

- `biography_pages`
  - 保存项目页、图片路径、OCR 产物路径、页状态
- `person_biographies`
  - 关联既有 `persons.id`
  - 保存原始列文本、横排文本、断句文本、白话文本

## 推荐执行顺序

1. 初始化项目目录和页图。
2. 每页输出 OCR 初稿，保留标题候选和原始列顺序。
3. 人工把标题人物关联到 `persons`。
4. 人工把正文列挂到正确人物，并写入 `source_text_linear`。
5. 项目整本完成后，批量调用 LLM 做断句和白话。
6. 最后抽样复核，再进入下游使用。

## LLM 后处理

人物小传在人工整理完成后，数据库里已经有三类文本位：

- `source_text_linear`
  - 人工拼接后的原始横排文本
- `source_text_punctuated`
  - 断句后的文言文本
- `source_text_baihua`
  - 白话文版本

当前推荐做法：

1. 先完成整本项目的人物关联与正文拼接。
2. 再统一跑一次 LLM 后处理，避免边校对边反复覆盖。
3. 对结果做抽样检查，重点看人名、亲属关系、地名、年号、葬地是否失真。

## 批处理脚本

脚本：

- `scripts/generate_biography_derivatives.py`

用途：

- 从 SQLite 读取某个 `project_id` 下的 `person_biographies`
- 以 `source_text_linear` 为输入
- 生成：
  - `source_text_punctuated`
  - `source_text_baihua`
  - `source_text_translation_notes`

默认规则：

- 只处理 `match_status = 'reviewed_manual'`
- 只处理 `source_text_linear` 非空的记录
- 若 `source_text_punctuated` 为空，或仍与 `source_text_linear` 完全相同，则视为“尚未真正断句”
- 若 `source_text_baihua` 为空，则视为“尚未生成白话”

## 运行方式

先看待处理数量：

```bash
python3 scripts/generate_biography_derivatives.py \
  --project-id bio_001_092_qianbian \
  --dry-run
```

正式跑整本：

```bash
python3 scripts/generate_biography_derivatives.py \
  --project-id bio_001_092_qianbian
```

只重跑某一人：

```bash
python3 scripts/generate_biography_derivatives.py \
  --project-id bio_001_092_qianbian \
  --person-id gen_001_005::p_11_003 \
  --force
```

只先跑前 10 条做验证：

```bash
python3 scripts/generate_biography_derivatives.py \
  --project-id bio_001_092_qianbian \
  --limit 10
```

## 凭证与模型

脚本支持两种提供方：

- OpenAI
  - 环境变量：`OPENAI_API_KEY`
  - 默认模型：`gpt-5`
- 阿里百炼 / DashScope
  - 环境变量：`DASHSCOPE_API_KEY`
  - 默认模型：`qwen-plus`
- Xiaomi Mimo
  - 环境变量：`MIMO_API_KEY`
  - 默认模型：`mimo-v2-flash`

若同时存在，默认优先 `OPENAI_API_KEY`，其次 `DASHSCOPE_API_KEY`。
也可以显式指定：

```bash
python3 scripts/generate_biography_derivatives.py \
  --project-id bio_001_092_qianbian \
  --provider openai \
  --model gpt-5
```

阿里百炼示例：

```bash
python3 scripts/generate_biography_derivatives.py \
  --project-id bio_001_092_qianbian \
  --provider dashscope \
  --model qwen-plus
```

## 与 review UI 的关系

人物小传 review UI 回写 SQLite 时：

- `source_text_linear` 继续由人工校对结果覆盖
- `source_text_punctuated`
- `source_text_baihua`
- `source_text_translation_notes`

以上三个字段若本次 UI 未提供，就保留数据库中的既有值，不再用 `linear_text` 覆盖。

这意味着：

- 先完成人工整理
- 再跑 LLM 后处理
- 后续若仅微调 OCR 挂接或正文块，LLM 结果不会被 UI 自动抹掉
