# 微信造物台

面向微信生态的内部内容生产流水线。当前完整实现表情包、红包封面和小程序版本发布三条并行产线。

## 已实现

- Django 模块化单体：项目/IP/热点、资产版本、平台规则、表情包生产、审计与权限
- Django Templates 负责页面骨架，Vue 3 + Element Plus 以 island 形式承载制作台交互
- 静态 PNG：语义策划、AI/本地生成、候选选稿、人工上传、审核、QA、投稿 ZIP
- 动态 GIF：从静态母图生成序列帧、调整顺序和帧时长、重新合成、体积与帧数校验
- 表情包独立工作区：专辑列表、默认/常用提示词库、逐项提示词编辑与优化
- 红包封面：封面故事、候选生成/上传、选稿、权利与技术 QA、投稿 ZIP、微信反馈、下单库存与渠道发放
- 小程序：PRD、构建包、体验码、审核截图、隐私清单、测试用例、审核 ZIP、微信审核与发布
- OpenAI 与本地演示提供商；缺少外部密钥只阻塞对应任务，不影响其他生产
- 人工微信投稿登记、驳回返修、审核通过、上架和指标快照
- Docker Compose：Postgres、Redis、MinIO、Django/Gunicorn、Celery worker/beat、Nginx
- 可复现规则快照、导出清单、权利材料目录和状态审计

详细业务与架构见 [docs/业务与架构.md](docs/业务与架构.md)，产品和界面约束见 [PRODUCT.md](PRODUCT.md) 与 [DESIGN.md](DESIGN.md)。

## 一键启动

需要 Docker 与 Docker Compose。

```bash
./scripts/init-env.sh
docker compose up -d --build
docker compose exec -T web .venv/bin/python manage.py seed_demo --produce
```

初始化脚本只在 `.env` 不存在时创建随机密钥，并输出首次管理员账号。默认访问：

- 工作台：<http://127.0.0.1:8080>
- MinIO 控制台：<http://127.0.0.1:9001>

若端口冲突，在 `.env` 修改 `APP_PORT` 后重新执行 `docker compose up -d`。数据使用 `data/postgres`、`data/redis`、`data/minio` 等 bind mount，不依赖匿名数据卷。

通过局域网 IP 访问时，还需把该 IP 加入 `DJANGO_ALLOWED_HOSTS`，并把带协议和端口的完整地址加入 `DJANGO_CSRF_TRUSTED_ORIGINS`，例如 `http://192.168.124.2:18082`。

常用运维命令：

```bash
docker compose ps
docker compose logs -f web worker
docker compose exec -T web .venv/bin/python manage.py bootstrap_pipeline
docker compose exec -T web .venv/bin/python manage.py seed_demo
```

`seed_demo --produce` 会幂等创建“团团”原创 IP、静态/动态表情专辑、红包封面项目和小程序版本，并生成本地案例资产，不消耗外部 API。

## OpenAI

在 `.env` 设置：

```dotenv
OPENAI_API_KEY=
OPENAI_TEXT_MODEL=gpt-5.6-terra
OPENAI_IMAGE_MODEL=gpt-image-2
QWEN_TEXT_MODEL=qwen3.7-plus
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
DASHSCOPE_API_KEY=
DEFAULT_AI_PROVIDER=local
```

制作台可分别选择策划/提示词模型（本地、OpenAI、Qwen）和生图模型（本地、OpenAI）。密钥为空时，任务会进入“等待外部配置”，错误可见且不会覆盖已有候选。生产环境应由密钥管理服务注入 `.env` 等价变量，不提交密钥文件。

`qwen3.7-plus` 接入语义策划和提示词优化，不作为生图模型：它可以理解图片，但输出模态是文本。实际生图仍需选择 `gpt-image-2`，或后续接入百炼的 `qwen-image-2.0-pro` / `wan2.7-image-pro`。后端服务必须使用百炼按量付费 API Key；Coding Plan 和 Token Plan Key 仅限交互式开发工具，不能供本服务调用。

## 本地开发

```bash
UV_CACHE_DIR=/tmp/uv-cache uv sync
bun install
bun run build
UV_CACHE_DIR=/tmp/uv-cache uv run python manage.py migrate
UV_CACHE_DIR=/tmp/uv-cache uv run python manage.py bootstrap_pipeline
CELERY_TASK_ALWAYS_EAGER=1 UV_CACHE_DIR=/tmp/uv-cache uv run python manage.py runserver
```

检查与测试：

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q
bun run build
docker compose config --quiet
```

## 上线前需要统一确认

这些事项不阻塞本地完整演示，但正式投稿或接入外部生产时需要人工补齐：

1. 在微信表情开放平台复核当期尺寸、体积、数量和权利材料要求，新建规则版本后再投稿；仓库内 `2026-07-seed` 只是可运行种子。
   红包封面与小程序同样需要按各自平台当期要求建立已确认规则版本。
2. 配置真实 OpenAI 密钥，确认组织允许使用的文本/图像模型、预算和数据处理边界。
3. 上传正式 IP 三视图、色板、禁用元素和著作权/授权证明。
4. 接入即梦前提供 API 文档、鉴权方式、回调协议和账号额度；现有 `AIProvider` 接口可直接扩展。
5. 生产部署确认域名、HTTPS、对象存储暴露策略、数据库备份与日志留存周期。
