FROM python:3.10.20-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PYTHONUTF8=1 \
    NODE_ENV=production

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN python --version && node --version

COPY requirements-docker.txt .
RUN pip install --no-cache-dir -r requirements-docker.txt

# 直播间监听仅需 jsrsasign，避免 sdenv/canvas 等原生模块编译失败
COPY package-docker.json package.json
RUN npm install --omit=dev && npm cache clean --force

COPY . .

CMD ["python", "launcher.py"]
