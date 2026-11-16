# 竞品价格监控 → 飞书，一条命令起一个常驻监控
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PRICE_CONFIG=/app/config.json \
    TZ=Asia/Shanghai

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY price_radar ./price_radar
COPY fixtures ./fixtures
COPY config.example.json ./config.json

VOLUME ["/app/data", "/app/out"]
CMD ["python", "-m", "price_radar", "watch"]
