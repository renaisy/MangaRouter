# 成本看板镜像
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

ENV TZ=Asia/Shanghai
EXPOSE 18502

CMD ["streamlit", "run", "app.py", \
     "--server.port=18502", \
     "--server.address=0.0.0.0", \
     "--server.headless=true"]
