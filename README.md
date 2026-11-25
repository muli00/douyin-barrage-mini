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

## 快速启动（仅抓弹幕）

```bash
cd ~/douyin-barrage-mini
LIVE_URL="https://live.douyin.com/你的直播间号" docker compose up --build
```

- 默认**只输出聊天弹幕**（`ONLY_CHAT=true`）；如需输出进房、点赞、礼物等全部消息，加上 `ONLY_CHAT=false`。
- `--build`（全称 **Build**）：启动前检查 `Dockerfile` 并构建镜像。

## 开启 AI 助播（方法一：`cookies.json` 登录）

1. **配置环境变量**：复制 `.env.example` 为 `.env`，填入你的大模型 `LLM_API_KEY`、`LIVE_URL` 和助播小号昵称 `BOT_NICKNAME`。
2. **编写知识库**：按你的直播间实际情况修改 `knowledge.txt`。
3. **导出登录 Cookie**：
   - 在 Mac 的 Chrome 浏览器中登录你的助播抖音小号并打开 `https://live.douyin.com/`；
   - 使用 Chrome 扩展（如 `Cookie-Editor`）导出 JSON 格式 Cookie，保存为项目根目录下的 `cookies.json`（已被 `.gitignore` 忽略）。
4. **先用演习模式试车**（`.env` 默认 `DRY_RUN=true`，AI 只打印回复内容，不真发）：
   ```bash
   docker compose up
   ```
5. **正式上线**：确认 AI 回复质量和频率满意后，把 `.env` 里的 `DRY_RUN=false` 即可自动在直播间公屏回复。

## 停止与自测

```bash
# 停止并清理容器
docker compose down

# 运行 5 项全链路自测
docker compose run --rm douyin python test_verify.py
```
