# MangaRouter 同机 ComfyUI（CPU）：Seedance 等 partner 节点走云端 API，无需 GPU
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
      git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/ComfyUI

# 固定浅克隆；无对应 tag 时回退默认分支
ARG COMFYUI_REF=master
RUN git clone --depth 1 --branch "${COMFYUI_REF}" \
      https://github.com/comfyanonymous/ComfyUI.git . \
    || git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git .

# CPU 版 torch，再装 ComfyUI 依赖
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

# Manager 打进镜像；运行时若卷覆盖 custom_nodes，由 entrypoint 补装
RUN git clone --depth 1 https://github.com/ltdrdata/ComfyUI-Manager.git \
      /opt/ComfyUI-Manager.bundle \
    && cp -a /opt/ComfyUI-Manager.bundle /opt/ComfyUI/custom_nodes/ComfyUI-Manager

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh \
    && mkdir -p /opt/ComfyUI/input /opt/ComfyUI/output /opt/ComfyUI/user /opt/ComfyUI/custom_nodes

# 卷挂载常用 root 写权限；仅本机回环暴露，经 Caddy basicauth
EXPOSE 8188

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "main.py", "--listen", "0.0.0.0", "--port", "8188", "--cpu", "--enable-cors-header"]
