# 更新日志

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。
格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

> 路线图见 [`docs/迭代计划.md`](docs/迭代计划.md)。安全红线见 [`docs/安全审查.md`](docs/安全审查.md) / [`docs/RULES.md`](docs/RULES.md)。主部署为腾讯云 VPS。

---

## [0.4.1] - 2026-08-09

### 对抗性安全热修（公网 VPS）

- **Streamlit**：submit / dash 不再把 Token、Base URL 预填或允许页面篡改（防密钥泄露与 SSRF）
- **Caddy**：`submit`/`dash` 增加 `basicauth` 模板；MinIO 控制台默认不对公网
- **adapter**：`ADAPTER_REQUIRE_AUTH=true` 时未配置 token 拒绝服务；`extra_params` 白名单
- **归档/ImageUrl**：https + Host 白名单、成片体积上限、object_prefix 消毒；删除预签名 Host 改写兜底
- **文档**：新增 `docs/安全审查.md`、`docs/RULES.md`

### 测试
- submit-tool 安全单测扩展；全量 pytest 回归

---

## [0.4.0] - 2026-08-09

### PDCA 合入：腾讯云 VPS 主部署 + 异步协作闭环

#### C1 部署与 P0
- **腾讯云 VPS**：新增 `deploy/Caddyfile`、`vps-setup.sh`、`backup.sh`、nginx 临时示例
- **compose**：submit 走 `http://new-api:3000`；新增 `submit-worker`；去掉直连 adapter 的 `ADAPTER_URL`
- **预签名图传**：MinIO 私有桶 + 公网 `SUBMIT_MINIO_PUBLIC_ENDPOINT` 预签名 URL
- **adapter 鉴权**：`ADAPTER_API_TOKEN` Bearer；`/health` 仍公开
- **cost-sync**：仅同步成功时写 `last_success_ts`
- **ComfyUI**：修复 `_upload_to_comfyui` NameError；上传使用 uuid 文件名

#### C2/C3 提交闭环
- NocoDB 批量 pending → 异步 TaskId + running；worker 归档并回填 ShareUrl/MinioPath/ErrorMsg
- 可选 `REVIEW_WEBHOOK_URL`；Storyboards 字段扩展（含 ProjectKey）

#### C4 质量
- cost-dashboard 边界处理；`COST_QUOTA_PER_YUAN`；GitHub Actions CI；备份脚本
- 重写部署指南 / 操作手册 / README / 迭代计划

### 测试
- 新增 adapter 鉴权与 submit-tool 单测；原有套件回归

---

## [0.3.3] - 2026-08-09

### P2 健壮性与运维加固（第二阶段）

#### cost-sync 健壮性（防静默漏数据）
- **newapi_client 分页上限保护**：新增 `max_pages` 参数（默认 1000 页=10万条），
  防止服务端 total 异常导致无限翻页
- **total 合理性校验**：负数视为脏数据告警退出，而非静默漏数据或死循环
- **HTTP 错误包装**：4xx/5xx 包装成 RuntimeError 给可读提示（如"请检查 token 权限"），
  而非裸 httpx 堆栈；非 JSON 响应也包装
- **aggregator created_at 异常跳过**：<=0 的脏记录跳过，避免算出 1970 年日期污染 Costs 表
- **aggregator 一次性 round**：金额累加原始 float，最后一次性 round，
  避免逐步 round 累积浮点偏差（成本核对时对不上）

#### compose 运维加固
- **自定义 networks**：显式声明 `seedance-net` 桥接网络，便于将来按安全边界分网
- **日志轮转**：长跑服务（new-api/nocodb/minio/两个mysql）加 `logging: json-file max-size:10m max-file:3`，防日志写爆磁盘
- **资源限制**：`mem_limit` 分配（mysql 1g、nocodb 2g、其余 1g），防 OOM 拖垮整机
- **mysql healthcheck 加 start_period: 30s**：冷启动期不误判 unhealthy

#### adapter 小改进
- **create_and_wait 首跳立即查询**：不再先 sleep 一个完整 interval，对快失败任务减少无谓等待
- **指数退避**：长任务轮询间隔指数增长（上限 60s），不再固定间隔频繁打上游
- **get_video 加 response_model**：OpenAPI schema 完整，前端可据此生成类型化客户端
- **lifespan 关闭判空**：启动期构造失败时 shutdown 不再 None.aclose() 崩溃
- **/health 收紧**：去掉 api_key_configured 字段，不向未授权方暴露密钥配置状态

### 测试
- cost-sync 新增 4 个用例（max_pages 上限、HTTP 错误包装、created_at 跳过、一次性 round）
- 全部 **42 个测试通过**（adapter 9 + cost-sync 18 + nocodb-init 15）

---

## [0.3.2] - 2026-08-09

### 验证发现的问题修复（重点验证 v0.3.1 改动后的真实联调）

#### 🔴 紧急修复：NocoDB PATCH 回归（v0.3.1 引入）
- **修复计费同步静默失败**：v0.3.1 把更新端点改成了 path 参数式
  `PATCH /records/{recordId}`，但 NocoDB v2 官方契约是 **body 带 Id 式**，
  path 参数式有已知 404 bug（GitHub Issue #11044/#11722/#11807）。
  回退为 `PATCH /records` + body `{"Id": id, ...fields}`，恢复计费同步更新能力

#### 🟠 Date 字段过滤
- `_find_existing` 对 Date 字段从 `eq` 改为 `exactDate` 关键字
  （NocoDB v2 对 Date 的可工作语法，避免底层时间分量匹配不上）

#### 🟠 镜像版本升级（v0.3.1 锁的 tag 过旧）
- `new-api`: `v0.6.0`(2025-03) → `v0.6.8.2`（v0.6 系列末版，不跨大版本）
- `nocodb`: `0.257.2`(2024-10) → `2026.08.0`（含 v2 PATCH 端点修复，与上面的修复配合）
- `mysql`: `8.0`(滚动) → `8.0.46`（锁 patch 版本保证可复现）
- minio/minio、minio/mc 保留（验证有效）

### P2 重构：nocodb-init 数据正确性（第一阶段）

#### dt 类型映射（影响最大，数据正确性根因）
- 新增 `UIDT_TO_DT` 映射表，建表时按 uidt 自动填底层 MySQL 类型
  （此前全为 `character varying`，导致数值/日期排序聚合退化为字符串比较）
- Number→int、Date→date、DateTime→timestamp、LongText→text 等
- 金额字段（Amount/Cost/Budget）显式标 `dt: decimal`，避免 int 丢小数

#### 建表幂等
- 新增 `list_existing_tables`，建表前先 GET 查重，已存在的表跳过
- 避免重跑时半失败残留不一致状态

#### 无人值守化（支持容器化/CI）
- `main()` 改用 argparse + 环境变量（`NOCODB_BASE_URL`/`NOCODB_TOKEN`/`NOCODB_BASE_ID`）
- `input()` 交互式仅在 `--interactive` 时兜底
- 可作为 compose 初始化任务或 CI 步骤运行

#### create_table 返回值校验
- 拿不到 tableId 时抛 `RuntimeError`，不再返回空串伪装成功

### 测试
- 新增 nocodb-init 测试套件 **15 个用例**（dt 映射、金额 decimal 校验、payload 构造、
  幂等查重、返回值校验）
- 全部 **38 个测试通过**（adapter 9 + cost-sync 14 + nocodb-init 15）

### 文档
- 部署指南：nocodb-init 改为支持环境变量/容器化运行

---

## [0.3.1] - 2026-08-09

### 代码审查后的修复（基于全面 review，覆盖全部 P0 + P1）

#### 🔴 P0 数据正确性
- **修复 `cost-sync/config.py` `_env` 忽略 default 参数**：默认 base_url 此前静默失效，
  改为正确透传 `os.environ.get(key, default)`
- **修复 `nocodb_writer` 去重键遗漏 Group 字段**：导致同日同人同模型同渠道但不同分组的
  聚合行互相覆盖（金额丢失）。去重键补齐为 5 字段，与 aggregator 一致
- **修复 NocoDB where 子句注入面**：新增 `_escape_where_value()`，对值做引号包裹 + 单引号转义，
  防止含 `,` `~` `()` 的渠道名/模型名破坏过滤或造成跨行污染
- **修复 submit-tool 虚假功能宣称**：移除"已自动归档到 MinIO"等与实现不符的注释，
  如实标注成片链接为方舟直链（有时效）；移除未被使用的 project/episode/shot_no 输入框
- **修复 adapter / submit-tool 未纳入 compose**：两个服务现在都在 docker-compose 里，
  与 README/文档"一键启动"的宣传一致；容器内用服务名互通，不再依赖 `--network host`
- **修复 `.env.example` 变量缺失与插值失效**：补全 `NOCODB_BASE_URL`/`NOCODB_TOKEN`/
  `STORYBOARDS_TABLE_ID`；`SUBMIT_MINIO_*` 改为显式值（`${VAR}` 在 --env-file 直灌时不展开）
- **修复 `submit-tool/Dockerfile` 漏 COPY**：`comfyui_bridge.py` 和 `templates/` 未拷进镜像，
  导致 ComfyUI 专业模式 import 失败

#### 🟠 P1 安全与健壮性
- **端口默认绑 127.0.0.1**：所有服务端口从 `0.0.0.0` 改为 `127.0.0.1:` 前缀，
  避免误暴露到公网（部署指南说明如何按需放开到 ZeroTier 网段）
- **所有业务容器以非 root 运行**：4 个 Dockerfile 统一加 `useradd app && USER app`
- **cost-sync 改用 loop 守护替代 cron**：cron 需 root 且 healthcheck 无效；
  改为 while+sleep loop 可非 root 运行，healthcheck 检查"最近成功时间戳"真正反映任务成败；
  调度参数 `COST_SYNC_INTERVAL_HOURS` 现在在 runtime 生效（原 cron 在 build 期固化失效）
- **业务镜像锁版本**：`minio`/`nocodb`/`new-api`/`mc` 从 `:latest` 改为具体 tag，保证可复现
- **MinIO healthcheck 改 HTTP 端点**：`mc ready local` 依赖 alias 配置，改用
  `curl /minio/health/ready` 更稳健
- **修复 adapter 非法 role 返回 500**：`ImageItem.role` 改用 Enum 字段，pydantic 自动返回 422
- **修复 `newapi_client` 数值字段遇 null 崩溃**：新增 `_to_int()` 兜底 None/bool/非数值
- **修复 `cost-dashboard` 换数据源不刷新**：`fetch_costs` 参数去掉下划线前缀
  （Streamlit cache_data 约定 `_` 开头参数不进缓存键）
- **ComfyUI 工作流错误透出**：`wait_result` 额外检查 `status_str=="success"`，
  失败时从 messages 提取错误详情，不再把失败当成功返回空输出
- **ComfyUI 输出 URL 编码**：`output_urls` 对 filename/subfolder 做 URL 编码，
  防含中文/空格/`&` 的文件名损坏 URL
- **submit-tool 文件上传安全加固**：用 uuid 重命名 + 后缀白名单 + 20MB 大小限制，
  杜绝文件名注入/路径穿越
- **适配器 `_parse` 防 JSONDecodeError**：2xx 非 JSON 响应包装成 VolcError，不再冒泡成 500
- **全项目加 `.dockerignore`**：防止 `.env`/`data`/缓存/测试/`.git` 烤进镜像层

#### 测试
- cost-sync 测试从 10 个增至 **14 个**（新增：Group 去重回归、where 转义、failed 计数、整天对齐）
- 全部 **23 个测试通过**（adapter 9 + cost-sync 14）
- `docker compose config` 验证合法

#### 文档
- 部署指南第 7、8 节：从"裸 docker run --network host"改为 compose 启动
- 9.5 节：`COST_SYNC_CRON` 改为 `COST_SYNC_INTERVAL_HOURS`

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
