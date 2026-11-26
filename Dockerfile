FROM python:3.11-slim

WORKDIR /app

# 安装 protoc 编译器与 Playwright 驱动所需的 libatomic1
RUN apt-get update && apt-get install -y --no-install-recommends \
    protobuf-compiler \
    libatomic1 \
    && rm -rf /var/lib/apt/lists/*

# 先独立安装并缓存体积最大的 Playwright 与 Chromium 内核（使用国内镜像源防海外 CDN 超时）
ENV PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright
RUN pip install --no-cache-dir "playwright>=1.49.0" \
    && playwright install --with-deps chromium

# 再安装项目其余 Python 依赖（后续增删依赖不再触发重下 Chromium）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目源码（开发时也会通过 docker-compose 的 volumes 挂载覆盖）
COPY . .

# 编译 Protobuf 生成 douyin_pb2.py
RUN protoc -I proto --python_out=. proto/douyin.proto

EXPOSE 8888 8889

CMD ["python", "-u", "main.py"]
