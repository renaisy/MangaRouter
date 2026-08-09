# 分镜批量提交小工具镜像
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py comfyui_bridge.py minio_store.py nocodb_client.py newapi_submit.py webhook_notify.py worker.py ./
COPY templates ./templates

# 非 root 运行（安全加固）
RUN useradd -r -u 1000 app && chown -R app /app
USER app

EXPOSE 18501

# 通过环境注入配置（详见 .env.example）
CMD ["streamlit", "run", "app.py", \
     "--server.port=18501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true"]
