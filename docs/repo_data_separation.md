# 代码仓库 / 数据仓库分离

目标是让 Git 仓库只保留代码、文档、schema、少量模板和必要 JSON；把大体积原始资料与派生资源放到仓库外。

## 目标结构

仓库外目录（默认）：

`/Users/rainwu/Projects/workspace_data/`

- `pdf/`
- `groups/`
- `bridges/`
- `ocr_cache/`
- `glyph_assets/`
- `sqlite/`
- `tmp/`

说明：

- 脚本默认支持通过环境变量 `FGB_WORKSPACE_DATA_ROOT` 覆盖数据根目录。
- 迁移后仓库内原路径会变成软链接，现有流程尽量不改。

## 迁移脚本

预览（不落盘）：

```bash
python3 scripts/separate_code_and_data.py
```

执行迁移：

```bash
python3 scripts/separate_code_and_data.py --execute
```

指定自定义数据根目录：

```bash
python3 scripts/separate_code_and_data.py --workspace-data-root /your/path/workspace_data --execute
```

## 关于 `genealogy.sqlite` 是否入 Git

建议默认不直接纳入主仓库版本管理，原因：

- 文件大、更新频繁，Git diff 几乎不可读。
- 容易带来冲突，且回滚粒度粗。

更稳妥的做法：

1. 主仓库只保留 `db/schema.sql` 和导入脚本。
2. SQLite 放在仓库外 `workspace_data/sqlite/`。
3. 重要里程碑用定期快照（例如按日期复制一份），或另建专门的数据仓库管理二进制资产。

