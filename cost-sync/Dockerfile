# 计费同步镜像：用 loop 守护替代 cron（更符合容器范式，可非 root 运行）
# 默认每天凌晨同步昨天；间隔和参数由环境变量控制，runtime 生效
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 时区设为北京时间
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 调度参数（runtime 可覆盖）
# COST_SYNC_INTERVAL_HOURS：同步间隔（小时），默认 24（每天一次）
# COST_SYNC_ON_STARTUP：启动时是否立即跑一次（true/false），默认 true
# COST_SYNC_ARGS：传给 sync.py 的参数，默认 "--days 1"
ENV COST_SYNC_INTERVAL_HOURS=24
ENV COST_SYNC_ON_STARTUP=true
ENV COST_SYNC_ARGS="--days 1"

# 非 root 运行（loop 守护无需 root，比 cron 更安全）
RUN useradd -r -u 1000 app && chown -R app /app
USER app

# 用 loop 脚本替代 cron 守护：
#  - 启动时（可选）立即跑一次
#  - 之后每 N 小时跑一次
#  - 单次失败不影响下次，退出码写入状态文件供 healthcheck
RUN printf '#!/bin/sh\n\
set -e\n\
mkdir -p /tmp/cost-sync\n\
if [ "$COST_SYNC_ON_STARTUP" = "true" ]; then\n\
  echo "[$(date)] 启动时立即执行一次同步…"\n\
  python sync.py $COST_SYNC_ARGS > /tmp/cost-sync/last_run.log 2>&1 || echo "[$(date)] 启动同步失败（见日志）" >> /tmp/cost-sync/last_run.log\n\
  date +%s > /tmp/cost-sync/last_success_ts\n\
fi\n\
echo "[$(date)] 进入循环：每 $COST_SYNC_INTERVAL_HOURS 小时同步一次"\n\
while true; do\n\
  sleep $((${COST_SYNC_INTERVAL_HOURS:-24} * 3600))\n\
  echo "[$(date)] 开始定时同步…"\n\
  if python sync.py $COST_SYNC_ARGS >> /tmp/cost-sync/last_run.log 2>&1; then\n\
    date +%s > /tmp/cost-sync/last_success_ts\n\
    echo "[$(date)] 同步成功" >> /tmp/cost-sync/last_run.log\n\
  else\n\
    echo "[$(date)] 同步失败（见上方日志）" >> /tmp/cost-sync/last_run.log\n\
  fi\n\
done\n' > /app/entrypoint.sh && chmod +x /app/entrypoint.sh

# healthcheck：检查 1.5 倍间隔内有成功记录，证明任务真的在跑
HEALTHCHECK --interval=300s --timeout=10s --start-period=120s --retries=2 \
  CMD python -c "import os,time; ts=float(open('/tmp/cost-sync/last_success_ts').read()); age=time.time()-ts; import sys; sys.exit(0 if age < float(os.environ.get('COST_SYNC_INTERVAL_HOURS','24'))*3600*1.5 else 1)"

CMD ["/app/entrypoint.sh"]
