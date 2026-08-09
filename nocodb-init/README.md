# NocoDB 协作平台表结构

本目录用于一键初始化漫剧团队的协作表结构。

## 三张表的设计

### 1. Projects（项目表）
| 字段 | 类型 | 说明 |
|------|------|------|
| Title 剧名 | 文本 | 必填 |
| Episodes 集数 | 数字 | |
| Owner 负责人 | 文本 | |
| Deadline 截止日期 | 日期 | |
| Status 状态 | 单选 | 策划中/制作中/审核中/已完成/搁置 |
| Budget 总预算 | 数字 | 元 |
| Remark 备注 | 长文本 | |

### 2. Storyboards（分镜表）—— 提交工具读写这张
| 字段 | 类型 | 说明 |
|------|------|------|
| Project 项目 | 文本 | |
| Episode 集 | 文本 | |
| ShotNo 镜头号 | 文本 | 如 S01E03-L012 |
| Prompt 提示词 | 长文本 | 必填，核心字段 |
| ImageUrl 参考图URL | URL | 图生视频用 |
| **Priority 重要级** | 单选 | **草稿/日常/成片** → 决定路由到哪个价格分组 |
| Model 指定模型 | 文本 | 可选，覆盖默认 |
| **Status 状态** | 单选 | **pending/running/succeeded/failed**（提交工具据此筛选） |
| VideoUrl 成片链接 | URL | 自动回填 |
| MinioPath MinIO路径 | 文本 | 自动回填 |
| SubmittedAt 提交时间 | 日期时间 | 自动回填 |
| DurationSec 耗时 | 数字 | 秒 |
| Cost 花费 | 数字 | 元 |
| Review 审核意见 | 长文本 | |
| ReviewStatus 审核状态 | 单选 | 待审核/通过/打回 |
| Remark 备注 | 长文本 | |

### 3. Costs（成本表）
用于记录/同步每次调用的花费，便于按项目、人员、渠道统计。

## 一键初始化

```bash
cd nocodb-init
pip install httpx
python init_schema.py
```
按提示输入 NocoDB 地址、API Token、Base ID 即可。

> **如何拿 Base ID**：在 NocoDB 网页里新建一个空 Base，看浏览器地址栏，
> 形如 `http://localhost:18080/#/nc/p_xxxxxx`，`p_` 后面那串就是 Base ID。
>
> **如何拿 API Token**：在该 Base 的「项目设置 → API Tokens」里生成。
