# ComfyUI 接入指南（内部专家必读）

> 面向团队里将要成为"ComfyUI 专家"的 1-2 人。
> 目标：让你们掌握 ComfyUI，做出工作流模板，**让其他成员不学节点也能用上首尾帧、多参考图、角色一致性等高级能力**。

---

## 〇、为什么选 ComfyUI

| 理由 | 说明 |
|------|------|
| 行业事实标准 | 2026 年视频创作工具生态最丰富，节点/模板最多 |
| **不需本地 GPU** | Seedance 节点是**调云端 API**的，ComfyUI 只做"编排界面"，普通电脑能跑 |
| 原生支持 Seedance 全模式 | 官方 partner node 已支持文生(T2V)、首尾帧(FLF2V)、多参考图(R2V)、真人一致性 |
| 工作流可复用 | 搭一次存成模板，全团队复用，避免每人重复造轮子 |
| 与 New-API 协同 | 可配置成走 New-API 网关，统一计费和路由 |

**关键认知**：在这个团队里，ComfyUI **不是用来跑模型的**（模型在火山引擎云端跑），而是充当"高级创作界面"——用节点连线把首帧、尾帧、参考图、提示词组合起来，生成视频。

---

## 一、安装 ComfyUI（专家电脑，约 30 分钟）

### 方式 A：官方桌面版（最简单，推荐）
1. 下载 https://www.comfy.org/download 的桌面版（Windows/Mac）
2. 安装后启动，自动下载基础环境
3. 不需要装 CUDA、不需要显卡，因为用云端 API 节点

### 方式 B：手动安装（需要 Python 3.10+）
```bash
git clone https://github.com/comfyanonymous/ComfyUI
cd ComfyUI
pip install -r requirements.txt
python main.py --enable-cors-header --listen 0.0.0.0
```
- `--enable-cors-header`：**必须加**，否则 Streamlit 调用桥跨域被拦
- `--listen 0.0.0.0`：让团队内网可访问（仅 ZeroTier 内网，安全）

### 验证
浏览器打开 http://localhost:8188 ，看到节点编辑器即成功。

---

## 二、安装 Seedance 节点

### 官方 ByteDance Partner Node（首选）
1. ComfyUI 界面 → 右下角「Manager」→「Custom Nodes Manager」
2. 搜索 `ByteDance` 或 `Seedance`，安装官方节点包
3. 重启 ComfyUI

安装后会得到这些节点：
| 节点 | 功能 | 对应 Seedance 模式 |
|------|------|------------------|
| Seedance 2.0 (T2V) | 文生视频 | content=[text] |
| Seedance 2.0 (R2V) | 多参考图生视频 | content=[text, image×N(role=reference_image)] |
| **Seedance 2.0 (FLF2V)** | **首尾帧生视频** | content=[text, image(first_frame), image(last_frame)] |
| ByteDance Create Image/Video Asset | 建立角色资产 | 真人一致性前置 |
| Seedance 2.0 Real Human | 角色/真人一致性生成 | 复用 Group ID |

> 参考官方教程：https://docs.comfy.org/zh/tutorials/partner-nodes/bytedance/seedance-2-0

### 备选：第三方火山引擎插件
若官方节点未覆盖某版本，可装 `ComfyUI-Jimeng-API`（GitHub: fkxianzhou/ComfyUI-Jimeng-API），
直接填火山引擎 API Key 调用，同样支持 Seedance 2.0，无需本地 GPU。

---

## 三、配置 API 凭证

### 用火山引擎直连（简单）
节点里直接填火山方舟 API Key（在 https://console.volcengine.com/ark 创建）。
节点会直连火山引擎云端生成。

### 走 New-API 网关（推荐，统一计费/路由）
让 ComfyUI 也通过团队的 New-API 网关调用，好处：
- 所有调用统一计费，进 New-API 日志
- 自动享受智能路由（草稿/日常/成片分级）
- 避免在每台电脑都存 API Key

配置方法：在 ComfyUI 的 Seedance 节点里：
- **API Base URL** 填 New-API 地址（或适配器地址）：`http://<中央节点IP>:18008`
- **API Key** 填 New-API 的令牌（不是火山引擎原始 Key）

> 这样 ComfyUI → New-API/适配器 → 火山引擎，链路统一。

---

## 四、搭建并导出工作流（核心技能）

以**首尾帧工作流**为例，这是专家要掌握的标准动作：

### 第 1 步：搭工作流
1. 节点面板拖出：
   - 2 个 `LoadImage` 节点（分别加载首帧、尾帧）
   - 1 个 `Seedance 2.0 FLF2V` 节点
   - 1 个 `SaveVideo` 节点
2. 连线：LoadImage1 → FLF2V.first_frame；LoadImage2 → FLF2V.last_frame；FLF2V → SaveVideo
3. 在 FLF2V 节点填提示词、选模型、配 API Key/URL
4. 点 `Queue Prompt` 测试，能出视频即成功

### 第 2 步：导出为 API 格式（关键）
- 菜单 → **保存(API格式)** → 存成 `seedance_first_last_frame.json`
- 注意：是 **API 格式**不是普通格式！普通格式不能被程序调用

### 第 3 步：改成可复用模板（关键）
打开导出的 JSON，把要外部传入的值改成**占位符** `{{变量名}}`：
```json
{
  "1": { "class_type": "LoadImage", "inputs": { "image": "{{first_frame_img}}" } },
  "2": { "class_type": "LoadImage", "inputs": { "image": "{{last_frame_img}}" } },
  "3": { "class_type": "Seedance2_FLF2V", "inputs": { "prompt": "{{prompt}}", ... } }
}
```
**占位符命名约定**（Streamlit 调用桥会据此生成上传控件）：
| 命名 | 控件类型 |
|------|---------|
| `{{xxx_img}}` / `{{xxx_image}}` | 单图上传 |
| `{{xxx_list}}` / `{{refs_xxx}}` | 多图上传 |
| 其它 | 文本输入 |

### 第 4 步：放进模板目录
把改好的 JSON 放到中央节点的 `submit-tool/templates/` 目录，团队成员立即能在 Streamlit「专业模式」看到。

---

## 五、模板复用机制（让普通成员受益）

```
专家：搭工作流 → 导出API格式 → 加占位符 → 放 templates/
                                              ↓
普通成员：Streamlit 专业模式 → 选模板 → 传图填字 → 一键触发
                                              ↓
                              ComfyUI 后台执行 → 返回成片
```

这样**普通成员完全不碰节点**，却能用到首尾帧、多参考图、角色一致性等全部高级能力。

本仓库已提供 3 个模板骨架（需专家用真实导出结构替换）：
- `templates/seedance_first_last_frame.json` —— 首尾帧
- `templates/seedance_multi_reference.json` —— 多参考图
- `templates/seedance_real_human.json` —— 角色一致性

---

## 六、培训大纲（专家自学路径，约 1 周）

| 天 | 目标 | 资源 |
|----|------|------|
| Day 1 | 装好 ComfyUI，跑通官方 Seedance T2V 示例 | 官方教程 |
| Day 2 | 学会 LoadImage + FLF2V，做出第一个首尾帧视频 | 同上 |
| Day 3 | 学会 R2V 多参考图，理解角色图+场景图组合 | 官方 R2V 教程 |
| Day 4 | 学会「保存API格式」+ 改占位符，导出第一个模板 | 本指南第四节 |
| Day 5 | 学会 Real Human + Group ID，建立本剧主要角色资产 | 真人一致性教程 |
| Day 6 | 模板进 Streamlit + **归档闭环验收**（ShareUrl/MinioPath 进 NocoDB） | 本仓库 comfyui_bridge + 专业模式 |
| Day 7 | 沉淀：把好用的提示词、参数组合存进 NocoDB | — |

**学成标志**：能给同事的任意"我想要这个效果"需求，30 分钟内搭出工作流并存成模板；专业模式跑通后 NocoDB 可见 ShareUrl。

**验收（Day 6 Check）**
1. 用真实 API JSON 替换 `submit-tool/templates/` 骨架（未替换勿选该模板生产）
2. 配置 `COMFYUI_BASE_URL`，提交后页面预览成片
3. 确认 MinIO `projects/{ProjectKey}/comfyui/...` 有对象，NocoDB Status=succeeded 且 ShareUrl 非空

---

## 七、常见问题

**Q：ComfyUI 调用报 401/403？**
A：API Key 错了，或 New-API 令牌没绑定对应分组。检查令牌权限。

**Q：节点找不到 Seedance？**
A：Manager 里装 ByteDance 官方节点包后重启。仍找不到用第三方 Jimeng-API 插件替代。

**Q：Streamlit 专业模式提交后 ComfyUI 没反应？**
A：①ComfyUI 启动时要加 `--enable-cors-header`；②检查 ComfyUI 地址对不对；③看 ComfyUI 后台日志。

**Q：占位符没被替换？**
A：占位符必须独占一个值字段（`"image": "{{first_frame_img}}"`），不能写半截（`"image": "prefix_{{x}}"` 部分场景支持但建议整体占位）。

**Q：生成的视频在哪？**
A：ComfyUI 的 `output/` 目录；调用桥返回 `/view?...` URL；专业模式成功后会归档到 MinIO 并写 NocoDB ShareUrl。

**Q：Group ID 是什么，怎么管理？**
A：一个 Group ID 代表一个"已验证的角色身份"。为本剧每个主要角色各建一个，记在 NocoDB 项目表的备注里，全员复用。换剧要新建。

---

## 八、参考资源
- [ComfyUI 官方 Seedance 2.0 教程](https://docs.comfy.org/zh/tutorials/partner-nodes/bytedance/seedance-2-0)
- [ComfyUI Seedance 真人一致性](https://docs.comfy.org/zh/tutorials/partner-nodes/bytedance/seedance-2-0-real-human)
- [火山方舟 Seedance API 文档](https://docs.volcengine.com/docs/82379/1520757)
- [ComfyUI-Jimeng-API 插件](https://github.com/fkxianzhou/ComfyUI-Jimeng-API)
- [ComfyUI 官方下载](https://www.comfy.org/download)
