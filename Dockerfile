FROM python:3.11-slim

WORKDIR /app

# 安装 protoc 编译器与 Playwright 驱动所需的 libatomic1
RUN apt-get update && apt-get install -y --no-install-recommends \
    protobuf-compiler \
    libatomic1 \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 安装 Playwright Chromium 内核及所需的系统依赖库
RUN playwright install --with-deps chromium

# 复制项目源码（开发时也会通过 docker-compose 的 volumes 挂载覆盖）
COPY . .

# 编译 Protobuf 生成 douyin_pb2.py
RUN protoc -I proto --python_out=. proto/douyin.proto

EXPOSE 8888

CMD ["python", "-u", "main.py"]
