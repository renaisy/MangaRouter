# MangaRouter

> 漫剧团队的 **Seedance 智能路由 + 协作** 方案。  
> 默认部署在 **腾讯云 VPS**（HTTPS 子域名），开源组件 + 少量定制。

[![版本](https://img.shields.io/badge/version-0.8.1-blue)](./CHANGELOG.md)
[![License](https://img.shields.io/badge/license-MIT-green)](./LICENSE)
[![CI](https://img.shields.io/badge/CI-pytest-brightgreen)](./.github/workflows/ci.yml)

**现状（v0.8.1）**：VPS 协作闭环 ✅ · ComfyUI 可同机 profile 部署（`comfy.*`）✅ · admin-tool / 多剧 / 缓存 ✅

> 公网上线前必读：[`docs/安全审查.md`](docs/安全审查.md) · [`docs/RULES.md`](docs/RULES.md) · [`docs/部署指南.md`](docs/部署指南.md)

---

## 解决什么问题

| 痛点 | 方案 |
|------|------|
| 单渠道贵 | 多渠道 + draft/standard/final 分组路由 |
| 分散办公传文件 | NocoDB + MinIO，浏览器 HTTPS 访问 |
| 手动提交、丢任务 | 异步入队 + worker 回填归档 |
| 不知道花多少 | cost-sync + 成本看板 |
| 首尾帧/多参考图 | 标准模式 + 公网预签名图传 |

---

## 架构（腾讯云 VPS）

```
团队浏览器 ──HTTPS──► Caddy（仅 80/443）
                        ├ api / collab / submit / dash / admin / comfy / s3
Docker:
  submit-tool ──► New-API ──► seedance-adapter ──► 火山方舟
  submit-tool ──► comfyui（可选 profile；专业模式）
  admin-tool ──► New-API 管理 API
  submit-worker / cost-sync / cost-dashboard
```

详见 [`docs/部署指南.md`](docs/部署指南.md)。

---

## 快速开始（技术负责人）

1. 腾讯云 VPS（建议 ≥4C8G），安全组只开 **22/80/443**
2. `sudo bash deploy/vps-setup.sh`
3. `cp .env.example .env` 并填写密码、`VOLC_API_KEY`、`ADAPTER_API_TOKEN`、`SUBMIT_MINIO_PUBLIC_ENDPOINT`
4. 编辑 `deploy/Caddyfile` 域名 → `docker compose up -d` → reload Caddy
5. 按部署指南或 [`docs/管理员配置手册.md`](docs/管理员配置手册.md) 配置 New-API 渠道（Base URL=`http://seedance-adapter:18008` + Bearer）与 NocoDB 建表
6. **安全**：`caddy hash-password` 写入 Caddyfile；确认 submit/dash/**admin** 401；勿公网暴露 MinIO 控制台

团队成员看 [`docs/操作手册.md`](docs/操作手册.md)。规则见 [`docs/RULES.md`](docs/RULES.md)。

---

## 目录

```
deploy/           # Caddy / VPS 初始化 / 备份
seedance-adapter/ # FastAPI 方舟适配器（鉴权）
submit-tool/      # Streamlit 提交 + worker
admin-tool/       # Streamlit 管理员渠道/令牌配置
comfyui/          # 同机 ComfyUI（compose profile=comfyui）
cost-sync/        # 计费同步
cost-dashboard/   # 成本看板
nocodb-init/      # 表结构初始化
docs/             # 部署 / 操作 / 渠道 / 迭代
```

---

## 测试

```bash
cd seedance-adapter && python -m pytest
cd cost-sync && python -m pytest
cd nocodb-init && python -m pytest
cd submit-tool && python -m pytest
cd admin-tool && python -m pytest
```

---

## 迭代与安全

- 路线图：[`docs/迭代计划.md`](docs/迭代计划.md)
- `.env` 勿提交；公网务必 HTTPS + 强密码；adapter 须配置 `ADAPTER_API_TOKEN`

## 许可证

MIT — 见 [`LICENSE`](LICENSE)。
