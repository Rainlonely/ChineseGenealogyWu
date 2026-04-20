# ChineseGenealogyWu

开发快照仓库，用于基于当前族谱整理成果开展公众号/小程序开发。

## 包含内容
- scripts/: 数据处理与本地服务脚本
- docs/: 工作流与数据模型说明
- db/: SQLite schema
- configs/: 配置文件
- data/genealogy.sqlite: 当前主数据库快照
- data/genealogy_check.sqlite / genealogy_debug.sqlite: 辅助数据库快照

## 说明
原始 PDF、OCR 中间产物、图片资源、组工作区数据等大体积内容不包含在本仓库中。
家庭电脑上的生产校对流程继续进行，后续可通过替换最新 SQLite 快照同步数据。
