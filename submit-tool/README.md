# 分镜批量提交小工具

把 NocoDB 分镜表里的待提交行，按重要级自动路由到对应价格/质量分组的 Seedance 渠道，
成片下载后归档到 MinIO，并把状态回填到 NocoDB。

## 运行方式

### 方式一：本地直接跑（开发/调试）
```bash
cd submit-tool
pip install -r requirements.txt

# 配置环境（指向你的中央节点）
export SUBMIT_NEWAPI_BASE_URL=http://192.168.1.50:13000
export SUBMIT_NEWAPI_TOKEN=<New-API 令牌>
export NOCODB_BASE_URL=http://192.168.1.50:18080
export NOCODB_TOKEN=<NocoDB API Token>
export SUBMIT_MINIO_ENDPOINT=192.168.1.50:19000
export SUBMIT_MINIO_ACCESS_KEY=seedance-admin
export SUBMIT_MINIO_SECRET_KEY=<MinIO 密码>
export ADAPTER_URL=http://192.168.1.50:18008   # 若 New-API 未原生支持 Seedance

streamlit run app.py
```
浏览器打开 http://localhost:8501

### 方式二：Docker
```bash
docker build -t seedance-submit .
docker run -d --name seedance-submit -p 18501:18501 \
  --env-file ../.env \
  seedance-submit
```

## 使用步骤

1. 在侧边栏填好 New-API / NocoDB / MinIO 的连接信息
2. 在 NocoDB 里创建好分镜表（结构见 `nocodb-init/schema.sql`）
3. 把分镜的 `Status` 字段填为 `pending`，填好 `Prompt` 和 `Priority`
4. 在本工具里输入「NocoDB 分镜表 ID」（在 NocoDB 表格 URL 里，形如 `mt_xxxxx`）
5. 点击「刷新待提交分镜」→ 选择 → 「批量提交所选分镜」
6. 提交完成后，NocoDB 里的 `Status` 会变成 `succeeded`，`MinioPath` 指向成片

## 重要级路由映射

| Priority（NocoDB） | New-API 分组 | 默认模型 | 用途 |
|------------------|------------|---------|-----|
| 草稿 draft       | `draft`    | Seedance 2.0-mini | 快速试提示词，最便宜 |
| 日常 standard    | `standard` | Seedance 2.0-fast | 性价比主力 |
| 成片 final       | `final`    | Seedance 2.0      | 质量优先 |

> 也可在分镜行里填 `Model` 字段强制指定模型，覆盖上面的默认值。
