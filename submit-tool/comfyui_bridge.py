"""Streamlit → ComfyUI 调用桥。

让不会 ComfyUI 的普通成员，也能从简化工具里触发预设的 ComfyUI 工作流
（首尾帧、多参考图、角色一致性等复杂能力），由内部专家预制好模板。

原理：
    1. 内部专家在 ComfyUI 里搭好工作流，导出为 API 格式的 JSON，放进 templates/
    2. 本模块读取模板，把其中的「占位变量」替换成当前任务的实际值
       （prompt、首帧图 URL、尾帧图 URL、参考图列表等）
    3. 调用 ComfyUI 的 /prompt 接口提交工作流，拿到 prompt_id
    4. 轮询 /history/{prompt_id}，完成后取输出图片/视频
    5. （可选）把结果下载回 MinIO 归档

ComfyUI 需开启 --enable-cors-header 并对内网开放 API。
"""
from __future__ import annotations

import time
from typing import Any

import httpx


class ComfyUIError(RuntimeError):
    pass


class ComfyUIBridge:
    """与 ComfyUI 服务端交互的轻量客户端。"""

    def __init__(self, base_url: str, timeout: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._client.close()

    # ----------------------- 健康检查 -----------------------
    def health(self) -> bool:
        try:
            r = self._client.get(f"{self.base_url}/system_stats")
            return r.status_code == 200
        except Exception:
            return False

    # ----------------------- 提交工作流 -----------------------
    def submit(self, workflow: dict[str, Any]) -> str:
        """提交一个 API 格式的工作流，返回 prompt_id。

        workflow 结构：{"节点id": {"class_type": ..., "inputs": {...}}, ...}
        提交时需包成 {"prompt": workflow}。
        """
        r = self._client.post(f"{self.base_url}/prompt", json={"prompt": workflow})
        if r.status_code >= 400:
            raise ComfyUIError(f"提交工作流失败 HTTP {r.status_code}: {r.text}")
        data = r.json()
        pid = data.get("prompt_id")
        if not pid:
            raise ComfyUIError(f"未返回 prompt_id：{data}")
        return str(pid)

    # ----------------------- 轮询结果 -----------------------
    def wait_result(self, prompt_id: str, max_seconds: int = 900,
                    interval: int = 5) -> dict[str, Any]:
        """轮询直到工作流完成，返回 history 里该 prompt 的输出。"""
        deadline = time.time() + max_seconds
        while time.time() < deadline:
            r = self._client.get(f"{self.base_url}/history/{prompt_id}")
            if r.status_code == 200:
                data = r.json()
                # 完成后 history 里会有这个 prompt_id 的条目
                entry = data.get(prompt_id)
                if entry and entry.get("status", {}).get("completed"):
                    return entry
            time.sleep(interval)
        raise ComfyUIError(f"工作流 {prompt_id} 超时（>{max_seconds}s）")

    def output_urls(self, history_entry: dict[str, Any]) -> list[str]:
        """从 history 条目里提取输出文件的相对路径，拼成可访问 URL。"""
        urls: list[str] = []
        outputs = history_entry.get("outputs", {})
        for node_out in outputs.values():
            # 视频输出常见字段：gifs/videos/images
            for key in ("gifs", "videos", "images"):
                for item in (node_out.get(key) or []):
                    fname = item.get("filename")
                    subfolder = item.get("subfolder", "")
                    ftype = item.get("type", "output")
                    if fname:
                        path = f"{subfolder}/{fname}" if subfolder else fname
                        urls.append(f"{self.base_url}/view?filename={path}&type={ftype}")
        return urls


def fill_template(template: dict[str, Any], variables: dict[str, Any]) -> dict[str, Any]:
    """把工作流模板里的占位变量替换成实际值。

    占位语法：节点 inputs 里的字符串值若形如 {{var_name}}，则用 variables["var_name"] 替换。
    支持替换为标量（str/int）或列表（多参考图场景）。
    """
    import copy
    import re

    filled = copy.deepcopy(template)
    pattern = re.compile(r"\{\{(\w+)\}\}")

    def _replace(node: Any) -> Any:
        if isinstance(node, dict):
            return {k: _replace(v) for k, v in node.items()}
        if isinstance(node, list):
            return [_replace(x) for x in node]
        if isinstance(node, str):
            m = pattern.fullmatch(node.strip())
            if m and m.group(1) in variables:
                # 整体占位：直接替换为原始类型（可成列表）
                return variables[m.group(1)]
            # 局部占位：做字符串替换
            return pattern.sub(lambda mm: str(variables.get(mm.group(1), mm.group(0))), node)
        return node

    return _replace(filled)
