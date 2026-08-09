# Seedance 异步适配器镜像
FROM python:3.12-slim

WORKDIR /app

# 先装依赖（利用层缓存）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 再拷代码
COPY app ./app

# 非 root 运行（安全加固）
RUN useradd -r -u 1000 app && chown -R app /app
USER app

ENV HOST=0.0.0.0
EXPOSE 18008

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "18008"]
