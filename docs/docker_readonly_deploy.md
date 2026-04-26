# Docker 部署（backend + prototype）

该部署模式默认用于“只查看 + 允许姓名勘误直接更正”。

- 不包含任何 PaddleOCR / OCR 服务。
- 后端 API 启用只读开关，续修等写接口返回 `403`。
- 姓名勘误默认开启直接更正，用于当前二次校对阶段。
- `prototype` 通过 Nginx 反向代理到后端 API。

## 1. 启动

在仓库根目录执行：

```bash
docker compose up -d --build
```

访问：

- 前端原型：`http://127.0.0.1:18080/index.html`
- 手机原型：`http://127.0.0.1:18080/mobile.html`
- 健康检查：`http://127.0.0.1:18080/health`

可通过环境变量修改端口：

```bash
PROTOTYPE_PORT=28080 docker compose up -d --build
```

默认以本地图片模式启动，会把 iCloud 的 `workspace_data` 只读挂载进后端容器，用于加载人物小图：

```bash
export FGB_WORKSPACE_DATA_ROOT="$HOME/Library/Mobile Documents/com~apple~CloudDocs/workspace_data"
GENEALOGY_ASSET_MODE=local docker compose up -d --build
```

线上 OSS 图片模式：

```bash
GENEALOGY_ASSET_MODE=online \
GENEALOGY_OSS_BASE_URL="https://你的OSS或CDN域名" \
docker compose up -d --build
```

本地模式使用 `persons.glyph_asset_path`，前端访问 `/assets/glyph_assets/<file>`；在线模式使用 `persons.glyph_asset_oss_key` 拼接 `GENEALOGY_OSS_BASE_URL`。

## 2. 写入策略

`docker-compose.yml` 已配置：

- `GENEALOGY_READ_ONLY=1`
- `GENEALOGY_ALLOW_DIRECT_CORRECTIONS=1`
- `./data/genealogy.sqlite:/data/genealogy.sqlite`

这表示：

1. API 层拒绝续修提交、审核动作等写操作。
2. 姓名勘误提交后直接写入 `persons.name` / `canonical_name`。
3. 旧姓名会作为 `person_search_aliases` 保留，方便后续仍可搜索。
4. 容器内数据库文件是可写挂载，勘误会保存到 `data/genealogy.sqlite`。

如果要恢复完全只读模式：

```bash
GENEALOGY_ALLOW_DIRECT_CORRECTIONS=0 docker compose up -d
```

并将 `docker-compose.yml` 中数据库挂载改回：

```yaml
- ./data/genealogy.sqlite:/data/genealogy.sqlite:ro
```

## 3. 数据发布

线上只读库建议来自编辑机的发布快照：

1. 编辑机完成一轮校对/关联。
2. 导出 `genealogy.sqlite` 快照。
3. 用快照替换部署目录的 `data/genealogy.sqlite`。
4. `docker compose up -d` 重新拉起。

## 4. 何时开启线上编辑

建议在“编辑库基本完成”后再开启，优先做：

1. 明确审核流（建议与正式入库分离）。
2. 决定是否迁移到多写友好的数据库（如 Postgres）。
