# MangaRouter 工程规则

> 所有贡献者须遵守。最后更新：2026-08-09

---

## 一、部署与安全（红线）

1. **主部署**：腾讯云 VPS；安全组仅 **22 / 80 / 443**；compose 端口绑 `127.0.0.1`。
2. **密钥**：只进环境变量 / `.env`（已 gitignore）；**禁止**写入 Streamlit `text_input` 默认值或下发到浏览器。
3. **公网 UI**：`submit.*` / `dash.*` / `admin.*` 必须 Caddy `basicauth`（或等价 SSO）；`admin` 用户与 `team` **分开**；MinIO **控制台不对公网**。
4. **适配器**：生产 `ADAPTER_REQUIRE_AUTH=true` 且必须配置 `ADAPTER_API_TOKEN`；New-API 渠道密钥与之相同。
5. **出站 URL**：成片下载 / ImageUrl 必须 https + Host 白名单；禁止私网/metadata。
6. **预签名**：只用 `SUBMIT_MINIO_PUBLIC_ENDPOINT` 签名；禁止「内网签名再改 Host」。
7. **admin-tool**：`ADMIN_NEWAPI_TOKEN` 仅容器环境；页面只读展示「已配置/未配置」，禁止预填 Token。
8. **多剧**：业务对象路径必须落在 `projects/{ProjectKey}/`；提交 UI 必填 ProjectKey。
9. **上线**：`deploy/smoke-check.sh` 纳入发版 Check。

细节见 [`docs/安全审查.md`](docs/安全审查.md)、[`docs/部署指南.md`](docs/部署指南.md)。

---

## 二、Python 与测试

- 运行时 Python 3.12（Dockerfile）；本地可用 3.10+。
- 改动自研模块后须跑对应 `pytest`：
  - `seedance-adapter` / `cost-sync` / `nocodb-init` / `submit-tool` / `admin-tool`
- 禁止把真实密钥写入测试或文档示例（用占位符）。

---

## 三、文档与版本

- 用户可见能力须与代码一致；虚标能力先改文档或补齐实现。
- 版本与变更写入 `CHANGELOG.md`；路线图见 `docs/迭代计划.md`。
- Commit message 简洁说明「为什么」；中英文均可，与仓库历史风格一致。

---

## 四、依赖与镜像

- 优先 pin 镜像 tag；新增服务默认非 root、日志轮转、`mem_limit`。
- 安装 Python 包可用清华/阿里云镜像（个人环境），勿把镜像凭据提交进仓库。
