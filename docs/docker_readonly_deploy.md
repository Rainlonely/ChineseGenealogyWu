# Docker 只读部署（backend + prototype）

该部署模式用于线上“只查看、不编辑”。

- 不包含任何 PaddleOCR / OCR 服务。
- 后端 API 启用只读开关，所有写接口返回 `403`。
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

## 2. 只读策略

`docker-compose.yml` 已配置：

- `GENEALOGY_READ_ONLY=1`
- `./data/genealogy.sqlite:/data/genealogy.sqlite:ro`

这表示：

1. API 层拒绝写操作（提交续修、姓名勘误、审核动作）。
2. 容器内数据库文件是只读挂载。

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
