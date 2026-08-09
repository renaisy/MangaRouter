# 更新日志

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。
格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

---

## [0.3.0] - 2026-08-09

### 新增
- **成本看板**（`cost-dashboard/`）：Streamlit 可视化，含总花费 KPI（带环比）、每日趋势线、
  成员/渠道/模型排名、三档分组占比（draft/standard/final）、明细表
- **计费同步 Docker 化**：`cost-sync` 内置 cron，默认每天 01:05 自动同步，已接入 docker-compose
  - 支持 `COST_SYNC_CRON` / `COST_SYNC_ARGS` 环境变量调整调度频率
  - 支持手动触发：`docker compose run --rm cost-sync python sync.py --days 7`
- **提示词模板库表**（`PromptTemplates`）：沉淀成功提示词供全员复用，14 个字段
  含场景类型、输入模式、seed、效果评分、贡献人等
- 部署指南新增「成本看板与计费同步」章节（9.5）

### 变更
- `nocodb-init` 新增第 4 张表 PromptTemplates，Costs 表补充 Group 字段（计费同步会写入）
- README 目录结构与技术栈表更新，反映 cost-sync / cost-dashboard
- `.env.example` 新增 `DASH_PORT` 端口与看板相关配置

### 修复
- Costs 表建表脚本遗漏 Group 字段（计费同步脚本会写入该字段，已补）

---

## [0.2.0] - 2026-08-09

### 新增
- **首尾帧 / 多参考图 / 角色一致性支持**：Seedance 适配器全面重构
  - `image_url: str`（单图）→ `images: list[ImageInput]`（多图带 role）
  - 支持 `first_frame` / `last_frame` / `reference_image` 三种角色
  - 覆盖文生视频、首帧图生视频、首尾帧图生视频、多参考图四种模式
- **ComfyUI 集成**（行业事实标准，云端 API 无需本地 GPU）
  - 官方 ByteDance partner node 原生支持 T2V/R2V/FLF2V/真人一致性
  - 引入「混合方案」：专家做模板，成员零门槛使用
  - 新增 `submit-tool/comfyui_bridge.py`：Streamlit → ComfyUI 调用桥（占位符替换/提交/轮询）
  - 新增 3 个工作流模板骨架：首尾帧、多参考图、角色一致性
- **ComfyUI 接入指南**（`docs/ComfyUI接入指南.md`）：含 7 天培训大纲
- **第三方渠道接入实例**（`docs/第三方渠道接入实例.md`）：聚合渠道省钱兜底配置
- **提示词工程最佳实践**（`docs/提示词工程最佳实践.md`）：漫剧专用，六要素结构 + 5 个场景模板
- submit-tool 重构为双模式：标准模式（首尾帧/多参考图上传）+ ComfyUI 专业模式

### 变更
- 适配器测试从 5 个增至 9 个（新增首尾帧、多参考图、纯文生、首帧单图用例）

---

## [0.1.0] - 2026-08-08

### 首次发布

#### 核心基础设施（一键 `docker compose up -d`）
- **New-API 智能路由网关**：多渠道接入、权重负载均衡、分级路由、按人计量计费
- **NocoDB 低代码协作平台**：项目/分镜/审核/成本管理，浏览器即用
- **MinIO 对象存储**：素材库与成片归档，S3 兼容
- **ZeroTier 分布式组网**：免费 P2P，10 人分散办公如局域网

#### 智能路由策略（核心省钱点）
- 按镜头重要级自动分流：草稿(draft)→便宜、日常(standard)→性价比、成片(final)→高质量
- 同组多渠道权重负载，官方高权重、聚合渠道兜底

#### 定制开发（最小化）
- **Seedance 异步适配器**（`seedance-adapter/`，FastAPI）：把火山方舟异步任务包装为统一接口
- **分镜批量提交工具**（`submit-tool/`，Streamlit）：批量提交 + 自动归档回填
- **NocoDB 表结构初始化**（`nocodb-init/`）：3 张表一键创建

#### 计费同步
- **cost-sync 模块**：New-API 消费日志 → NocoDB Costs 表，按日聚合 + 幂等去重

#### 文档
- 部署指南（技术篇）、操作手册（成员篇）、New-API 渠道配置详解

#### 测试
- 适配器 5 个单元测试、计费同步 10 个单元测试，全部通过
