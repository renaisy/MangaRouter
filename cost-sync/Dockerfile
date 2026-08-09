# 计费同步镜像：内置 cron，每天凌晨自动把 New-API 消费日志同步到 NocoDB
FROM python:3.12-slim

WORKDIR /app

# 装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 拷代码
COPY . .

# 时区设为北京时间（cron 和日志时间都用它）
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 装 cron
RUN apt-get update && apt-get install -y --no-install-recommends cron && rm -rf /var/lib/apt/lists/*

# cron 表达式可由环境变量 COST_SYNC_CRON 覆盖，默认每天凌晨 1:05 跑昨天的数据
ENV COST_SYNC_CRON="5 1 * * *"
ENV COST_SYNC_ARGS="--days 1"

# 用 envsubst 把环境变量注入 cron 任务（容器启动时执行）
RUN printf '#!/bin/sh\n\
set -e\n\
mkdir -p /var/log\n\
printenv | grep -E "^(COST_|TZ)" > /app/.cron.env\n\
echo "$COST_SYNC_CRON root . /app/.cron.env; cd /app && python sync.py $COST_SYNC_ARGS >> /var/log/cost-sync.log 2>&1" > /etc/cron.d/cost-sync\n\
chmod 0644 /etc/cron.d/cost-sync\n\
crontab /etc/cron.d/cost-sync\n\
echo "cron 已配置：$COST_SYNC_CRON 执行 python sync.py $COST_SYNC_ARGS"\n\
exec cron -f\n' > /app/entrypoint.sh && chmod +x /app/entrypoint.sh

# 健康检查：看 cron 进程在不在
HEALTHCHECK --interval=60s --timeout=5s --retries=3 \
  CMD pgrep cron > /dev/null || exit 1

CMD ["/app/entrypoint.sh"]
