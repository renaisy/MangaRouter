# MangaRouter 🎬

> 漫剧团队的 **Seedance 智能路由 + 本地/云端协同** 一体化方案。
> 全部基于开源项目 + 极少量定制开发，专为非开发背景团队设计。

[![版本](https://img.shields.io/badge/version-0.3.0-blue)](./CHANGELOG.md)
[![License](https://img.shields.io/badge/license-MIT-green)](./LICENSE)
[![测试](https://img.shields.io/badge/tests-19%20passed-brightgreen)](#-测试)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](./docs/迭代计划.md#七版本节奏)

**v0.3 现状**：智能路由 ✅ · 首尾帧/多参考图 ✅ · 角色一致性 ✅ · 成本看板 ✅ · ComfyUI 集成 ✅ · 分布式协同 ✅

> **v0.3 新增**：成本看板（可视化趋势/排名/三档占比）+ 计费同步 Docker 化（cron 自动跑）+ 提示词模板库
>
> **v0.2 新增**：首尾帧 / 多参考图 / 角色一致性支持，引入 ComfyUI 作为「专业创作界面」，
> 让少数专家做模板、多数成员零门槛使用。

---

## ✨ 这个项目解决什么

| 痛点 | 本方案 |
|------|--------|
| Seedance 官方只提供一个渠道，贵 | 多渠道接入 + 智能路由，草稿走便宜渠道、成片走高质量 |
| 10 人分散办公，靠网盘+微信传文件 | 统一协作平台 + 素材库，浏览器即用 |
| 每次手动一条条提交生成 | 批量提交工具，自动归档回填 |
| 不知道花了多少钱、谁花的 | 按人/项目/渠道的计费统计 |
| 首尾帧/多参考图/角色一致性不会用 | 标准模式支持四种输入模式 + ComfyUI 专业模式做复杂工作流 |
| 非技术人员用不了高级功能 | 专家做 ComfyUI 模板，成员在 Streamlit 一键触发 |

---

## 🏗️ 架构

```
团队成员（浏览器）
      │  ZeroTier 虚拟组网
      ▼
中央节点（团队内 1 台 24h 开机电脑）
  ├─ New-API    智能路由网关（多渠道/权重/分级路由/计费）
  ├─ NocoDB     低代码协作平台（项目/分镜/审核/成本）
  ├─ MinIO      对象存储（素材库/成片归档）
  ├─ 适配器     Seedance 异步任务包装，支持首尾帧/多参考图（v0.2）
  └─ 提交工具   标准模式(文生/首帧/首尾帧/多参考图) + ComfyUI专业模式
      │                                      ↑
      │                            ComfyUI（专家电脑，云端API无GPU）
      ▼
火山引擎方舟 / 第三方聚合渠道
```

**两种使用模式（v0.2 核心）**：
- **标准模式**：多数成员在 Streamlit 填表 + 上传首帧/尾帧/参考图，走 New-API 路由
- **ComfyUI 专业模式**：1-2 个专家用 ComfyUI 搭复杂工作流（角色一致性等），存成模板，成员在 Streamlit 触发

---

## 📦 目录结构

```
seedance-hub/
├── docker-compose.yml      # 一键启动 New-API + NocoDB + MinIO + 2 个 MySQL
├── .env.example            # 环境变量模板（复制为 .env 后填写）
├── seedance-adapter/       # 定制件A：Seedance 异步适配器（FastAPI，按需）
│   ├── app/                #   config / volc_client / main
│   ├── tests/              #   单元测试（已验证 5/5 通过）
│   ├── Dockerfile
│   └── requirements.txt
├── submit-tool/            # 定制件B：分镜提交工具（Streamlit，v0.2）
│   ├── app.py              #   标准模式(首尾帧/多参考图) + ComfyUI专业模式
│   ├── comfyui_bridge.py   #   Streamlit→ComfyUI 调用桥
│   ├── templates/          #   ComfyUI 工作流模板（首尾帧/多参考图/角色一致性）
│   ├── Dockerfile
│   └── requirements.txt
├── nocodb-init/            # 协作平台表结构一键初始化（4 张表，含提示词模板库）
│   ├── init_schema.py
│   └── README.md
├── cost-sync/              # 计费同步：New-API 消费日志 → NocoDB Costs 表
│   ├── sync.py             #   主入口（定时跑，--days / --date / --dry-run）
│   ├── newapi_client.py    #   New-API 日志拉取
│   ├── aggregator.py       #   按日×成员×模型×渠道聚合
│   ├── nocodb_writer.py    #   幂等写入（带去重）
│   ├── Dockerfile          #   内置 cron，进 compose 自动定时
│   └── tests/              #   10 个单测全过
├── cost-dashboard/         # 成本看板（Streamlit）：趋势/排名/三档占比可视化
│   ├── app.py
│   └── Dockerfile
├── docs/
│   ├── 部署指南.md         # 技术负责人看
│   ├── 操作手册.md         # 团队成员看
│   ├── New-API渠道配置.md  # 路由策略详解
│   ├── ComfyUI接入指南.md  # 内部专家必读
│   ├── 第三方渠道接入实例.md # 聚合渠道省钱兜底
│   ├── 提示词工程最佳实践.md # 漫剧专用提示词心法+模板
│   └── 迭代计划.md         # 下一阶段规划与优化方向
└── data/                   # 运行时数据（MySQL/MinIO，自动生成，勿删）
```

---

## 🚀 快速开始

### 技术负责人（搭建，2-3 小时）
1. 通读 [`docs/部署指南.md`](docs/部署指南.md)
2. 把本项目放到选定的**中央节点**主机上
3. `cp .env.example .env` → 编辑 `.env` 填密码
4. `docker compose up -d`
5. 按部署指南配置 ZeroTier、New-API 渠道、NocoDB 建表
6. 验证全流程

### 团队成员（使用，5 分钟）
1. 通读 [`docs/操作手册.md`](docs/操作手册.md)
2. 安装 ZeroTier 加入网络
3. 浏览器打开协作平台干活

---

## 💰 智能路由策略（核心省钱点）

利用 New-API 的「渠道分组」实现**按镜头重要级自动分流**：

| 重要级 | 路由分组 | 默认渠道 | 价格参考 | 用途 |
|--------|---------|---------|---------|------|
| 🟢 草稿 | `draft` | Seedance 2.0-mini / 聚合 | ~0.5 元/秒 | 试提示词、调构图 |
| 🟡 日常 | `standard` | Seedance 2.0-fast | ~0.7 元/秒 | 性价比主力 |
| 🔴 成片 | `final` | Seedance 2.0/2.5 官方 | ~1 元/秒 | 最终交付高质量 |
| ⚪ 兜底 | 同组低权重 | 第三方聚合 | 低 10-15% | 非紧急走量 |

> 实测经验：80% 的迭代走「草稿」档，整体成本可比「全用最高档」降低 60%+。
> 详见 [`docs/New-API渠道配置.md`](docs/New-API渠道配置.md)。

---

## 🧰 技术栈

| 组件 | 选型 | 开源协议 | 用途 |
|------|------|---------|------|
| 智能路由网关 | [New-API](https://github.com/QuantumNous/new-api) | MIT | 多渠道/权重/分级/计费 |
| 协作平台 | [NocoDB](https://github.com/nocodb/nocodb) | AGPL-3.0 | 低代码表格协作 |
| 对象存储 | [MinIO](https://github.com/minio/minio) | AGPL-3.0 | 素材库/成片归档 |
| 虚拟组网 | [ZeroTier](https://www.zerotier.com) | 商用免费 | 分布式团队组网 |
| **专业创作界面** | [ComfyUI](https://github.com/comfyanonymous/ComfyUI) | GPL-3.0 | v0.2：首尾帧/多参考图/角色一致性工作流（云端API，无GPU） |
| 适配器 | 本项目（FastAPI） | 随项目 | Seedance 异步包装，支持四种输入模式 |
| 提交工具 | 本项目（Streamlit） | 随项目 | 标准模式 + ComfyUI 模板触发 |

---

## 📋 待你确认/准备的事项

搭建前请准备：
- [ ] 选定中央节点主机（8G+ 内存，可 24h 开机）
- [ ] 火山引擎账号已实名 + 开通 Seedance 模型权限
- [ ] （可选）1-2 家第三方聚合渠道账号
- [ ] 决定组网方案（ZeroTier 免费 / FRP 租 VPS）

---

## 🔒 安全提示
- `.env` 里的密码务必改成强随机串，**不要提交到 git**
- New-API 首次登录后立即改 root 密码
- 所有服务**只对内网/ZeroTier 开放**，不要直接暴露到公网
- 如需公网访问（出差/外网），务必加 HTTPS 和强密码

---

## 🧪 测试

```bash
cd seedance-adapter && python -m pytest      # 9 个用例
cd cost-sync && python -m pytest             # 10 个用例
```
合计 19 个单元测试，覆盖适配器多图能力、配额换算、聚合逻辑、幂等写入、时间范围边界。

---

## 🗺️ 迭代计划

详见 [`docs/迭代计划.md`](docs/迭代计划.md)。近期优先级：

- **P0**：成片预签名 URL 分享、审核通知自动化、ComfyUI 模板实战填充
- **P1**：多剧隔离、夜间批量调度、生成结果缓存去重、成本预警
- **P2**：多模型供应商抽象（可灵/即梦/Sora）、成片后处理流水线、角色资产库

版本变更见 [`CHANGELOG.md`](CHANGELOG.md)。

---

## 🤝 贡献

欢迎 Issue / PR！特别欢迎的方向：
1. 第三方渠道接入实测反馈（哪些聚合商真正支持首尾帧）
2. ComfyUI 工作流模板的真实化贡献
3. 多模型适配器扩展
4. 文档勘误与本地化

---

## 📄 许可证

MIT License — 详见 [`LICENSE`](LICENSE)。
