# 分镜提交小工具

经 **New-API** 按重要级路由到 Seedance 渠道；图片上传 MinIO 后使用**公网预签名 URL** 供方舟拉取；
任务异步入队，由 `submit-worker` 轮询完成后归档到 MinIO 并回填 NocoDB。

## 运行方式

### Docker（推荐，见仓库根 compose）
```bash
docker compose up -d submit-tool submit-worker
# 访问：https://submit.your.domain （经 Caddy）
```

### 本地调试
```bash
cd submit-tool
pip install -r requirements.txt
export SUBMIT_NEWAPI_BASE_URL=http://127.0.0.1:13000
export SUBMIT_NEWAPI_TOKEN=<令牌>
export NOCODB_BASE_URL=http://127.0.0.1:18080
export NOCODB_TOKEN=<token>
export STORYBOARDS_TABLE_ID=<mt_xxx>
export SUBMIT_MINIO_ENDPOINT=127.0.0.1:19000
export SUBMIT_MINIO_ACCESS_KEY=seedance-admin
export SUBMIT_MINIO_SECRET_KEY=<密码>
export SUBMIT_MINIO_PUBLIC_ENDPOINT=s3.your.domain
export SUBMIT_MINIO_PUBLIC_SECURE=true
streamlit run app.py
# 另开终端：python worker.py
```

## 使用步骤

1. 环境变量或侧边栏（管理员展开区）配置 New-API / NocoDB / 表 ID
2. 用 `nocodb-init/init_schema.py` 建好 Storyboards（含 TaskId / ShareUrl / ErrorMsg）
3. **批量**：分镜 `Status=pending` → 「NocoDB 批量提交」勾选提交
4. **单条**：标准提交填提示词/图 → 异步提交
5. worker 将 `running` → `succeeded`，写入 `VideoUrl` / `MinioPath` / `ShareUrl`

## 重要级路由

| Priority | New-API 分组 | 默认模型 |
|----------|-------------|---------|
| 草稿 | `draft` | Seedance 2.0-mini |
| 日常 | `standard` | Seedance 2.0-fast |
| 成片 | `final` | Seedance 2.0 |

通过 `X-New-Api-Group` +（可选）分档令牌 `SUBMIT_TOKEN_*` 选择分组；**不会**把 group 塞进方舟 `extra_params`。

## ComfyUI 专业模式

模板目录 `templates/` 内为骨架，需专家导出真实 API JSON 替换后方可生产使用。
