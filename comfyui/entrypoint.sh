#!/bin/sh
set -eu
# 若挂载了空的 custom_nodes 卷，补回 Manager
if [ ! -d /opt/ComfyUI/custom_nodes/ComfyUI-Manager ]; then
  mkdir -p /opt/ComfyUI/custom_nodes
  cp -a /opt/ComfyUI-Manager.bundle /opt/ComfyUI/custom_nodes/ComfyUI-Manager
fi
mkdir -p /opt/ComfyUI/input /opt/ComfyUI/output /opt/ComfyUI/user
exec "$@"
