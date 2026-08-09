# 成本看板镜像
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

# 非 root 运行（安全加固）
RUN useradd -r -u 1000 app && chown -R app /app
USER app

ENV TZ=Asia/Shanghai
EXPOSE 18502

CMD ["streamlit", "run", "app.py", \
     "--server.port=18502", \
     "--server.address=0.0.0.0", \
     "--server.headless=true"]
