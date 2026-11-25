# douyin-barrage-mini（抖音直播弹幕抓取 + AI 助播 · Docker 版）

基于 **Playwright + CDP 拦截 WSS + Protobuf 解包 + 本地 WebSocket 广播 + 在线大模型 AI 助播** 的简化版项目，全部运行在 Docker 容器中，保持 Mac 本地环境零污染。

## 目录结构

```text
douyin-barrage-mini/
├── Dockerfile                # 容器环境图纸（Python + protoc + Playwright + Chromium）
├── docker-compose.yml        # 一键启动清单（目录挂载 + 8888 端口映射）
├── .devcontainer/
│   └── devcontainer.json     # VS Code Dev Containers 配置
├── .env.example              # 环境变量配置模板（复制为 .env 使用）
├── knowledge.txt             # AI 助播人设与直播间商品/QA 知识库
├── proto/
│   └── douyin.proto          # 抖音核心消息 Protobuf 定义
├── douyin_pb2.py             # protoc 自动生成的 Python 解析类
├── decoder.py                # Base64 → PushFrame → gzip → Response → 统一 JSON
├── ws_server.py              # 本地 WebSocket 广播服务（0.0.0.0:8888）
├── ai_assistant.py           # AI 助播大脑（OpenAI 兼容接口 + 过滤 + 违禁词 + 冷却）
├── sender.py                 # Cookie 注入（方法一）+ Playwright 自动发送弹幕
├── main.py                   # 主入口（串联抓取、广播与 AI 助播）
├── test_client.py            # 下游 WebSocket 测试接收客户端
└── test_verify.py            # 全链路自测脚本
```

## 快速启动（仅抓弹幕，无需开 Mac Chrome）

```bash
cd ~/douyin-barrage-mini
CDP_URL="" LIVE_URL="https://live.douyin.com/你的直播间号" docker compose up --build
```

- 默认**只输出聊天弹幕**（`ONLY_CHAT=true`）；如需输出进房、点赞、礼物等全部消息，加上 `ONLY_CHAT=false`。
- `--build`（全称 **Build**）：启动前检查 `Dockerfile` 并构建镜像。

## 开启 AI 助播（方式 A：Docker 直连 Mac 独立可视 Chrome）

1. **打开 Mac 独立助播 Chrome 窗口并扫码登录**：
   在第一个终端窗口运行（会弹出一个独立的 Chrome 窗口，与你平时用的 Chrome 完全隔离）：
   ```bash
   cd ~/douyin-barrage-mini
   bash start_mac_chrome.sh
   ```
   在弹出的窗口中手动扫码登录你的**助播抖音小号**（登录态自动保存在 `mac_chrome_profile/` 中，以后长期复用；运行期间保持该窗口开启即可）。
2. **配置环境变量**：复制 `.env.example` 为 `.env`，填入你的大模型 `LLM_API_KEY`、`LIVE_URL` 和助播小号昵称 `BOT_NICKNAME`。
3. **编写知识库**：按你的直播间实际情况修改 `knowledge.txt`。
4. **启动容器直连 Mac Chrome**：
   另开一个终端标签页（`Command + T`），运行：
   ```bash
   cd ~/douyin-barrage-mini
   docker compose up
   ```
   （演习模式 `DRY_RUN=true` 只打印回复不真发；确认满意后在 `.env` 设为 `DRY_RUN=false` 即可正式在公屏自动回复。）

## 停止与自测

```bash
# 停止并清理容器
docker compose down

# 运行 5 项全链路自测
docker compose run --rm douyin python test_verify.py
```
