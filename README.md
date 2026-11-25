# douyin-barrage-mini（抖音直播弹幕抓取简化版 · Docker 版）

基于 **Playwright + CDP 拦截 WSS + Protobuf 解包 + 本地 WebSocket 广播** 的极简抖音直播弹幕抓取项目，全部运行在 Docker 容器中，保持 Mac 本地环境零污染。

## 目录结构

```text
douyin-barrage-mini/
├── Dockerfile                # 容器环境图纸（Python + protoc + Playwright + Chromium）
├── docker-compose.yml        # 一键启动清单（目录挂载 + 8888 端口映射）
├── .devcontainer/
│   └── devcontainer.json     # VS Code Dev Containers 配置
├── proto/
│   └── douyin.proto          # 抖音核心消息 Protobuf 定义
├── douyin_pb2.py             # protoc 自动生成的 Python 解析类
├── decoder.py                # Base64 → PushFrame → gzip → Response → 统一 JSON
├── ws_server.py              # 本地 WebSocket 广播服务（0.0.0.0:8888）
├── main.py                   # 主入口（Playwright + CDP 拦截串联）
├── test_client.py            # 下游 WebSocket 测试接收客户端
└── test_verify.py            # 全链路自测脚本
```

## 快速启动

1. 进入项目目录并传入你想抓取的直播间网址启动：

```bash
cd ~/douyin-barrage-mini
LIVE_URL="https://live.douyin.com/你的直播间号" docker compose up --build
```

- 默认**只输出聊天弹幕**（`ONLY_CHAT=true`）；如需输出进房、点赞、礼物等全部消息，启动时加上 `ONLY_CHAT=false`：
  ```bash
  LIVE_URL="https://live.douyin.com/你的直播间号" ONLY_CHAT=false docker compose up
  ```
- `--build`（全称 **Build**）：启动前检查 `Dockerfile` 并构建镜像。

2. 停止并清理容器：

```bash
docker compose down
```

3. 另开一个终端测试接收 `ws://127.0.0.1:8888` 广播（可在容器内执行）：

```bash
docker compose exec douyin python test_client.py
```
