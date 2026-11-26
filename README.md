# douyin-barrage-mini（抖音直播弹幕抓取 + 双通道 AI 文字/语音助播 · Docker 版）

基于 **Playwright + CDP + Protobuf 解包 + 在线大模型 + `edge-tts` 双轨语音播报** 的极简直播助播工具，Python 环境全部隔离在 Docker 容器中。

## 目录结构

```text
douyin-barrage-mini/
├── Dockerfile                # 容器环境图纸（Python + protoc + Playwright + edge-tts）
├── docker-compose.yml        # 一键启动清单
├── .env.example              # 环境变量配置模板（复制为 .env 使用）
├── knowledge.txt             # 答疑知识库（公屏打字与语音答疑共用，改完保存热生效）
├── pitch.txt                 # 日常循环商品口播讲解稿（每行一句短话，改完保存热生效）
├── generate_pitch.py         # 喂入商品链接/卖点，AI 自动写口播稿写入 pitch.txt 并同步知识库
├── voice_speaker.py          # 双轨 TTS 语音调度（弹幕提问高优插播 + 平时循环讲品）
├── ai_assistant.py           # AI 大脑（一次请求同时产出公屏短回复 + 语音点名口播词）
├── sender.py                 # Playwright 自动公屏打字发送
├── start_mac_chrome.sh       # 启动 Mac 独立可视 Chrome 并后台开启 afplay 本地语音播报
├── play_audio.sh             # 单独启动 Mac 本地 afplay 语音监听播放脚本
├── main.py                   # 主入口
└── test_verify.py            # 6 项全链路自测脚本
```

## 完整使用流程（手机直播 + AI 语音讲品 + 双通道答疑）

### 1. 打开 Mac 独立浏览器与本地声音输出
在**终端 1** 运行（会弹出独立 Chrome 窗口，并自动在后台启动 `afplay` 监听播放 AI 语音，可通过直播内录线传给手机或外放）：

```bash
cd ~/douyin-barrage-mini
bash start_mac_chrome.sh
```
首次打开在窗口中扫码登录助播抖音小号，之后长期免登。

### 2.（可选）喂入商品链接，让 AI 自动生成口播稿与答疑知识
在**终端 2** 运行（自动借用已登录的 Mac Chrome 提取商品页标题与参数，生成短句写入 `pitch.txt` 并追加到 `knowledge.txt`）：

```bash
cd ~/douyin-barrage-mini
docker compose run --rm douyin python -u generate_pitch.py "https://商品链接" "1号链接活动价59元，杭州现货48小时发"
```

也可以直接用编辑器手动修改 `pitch.txt` 和 `knowledge.txt`（直播运行中途修改保存立即热生效）。

### 3. 开启直播间抓取 + 语音循环讲品 + 弹幕双通道答疑
确保 `.env` 中已设置 `AI_ENABLED=true`、`VOICE_ENABLED=true`，在**终端 2** 运行：

```bash
docker compose up
```

- **没人提问时**：按句循环朗读 `pitch.txt` 讲解商品；
- **有观众发弹幕提问时**：等当前这句短话自然念完，下一句立刻无缝**语音点名插播答疑**，同时助播小号在**公屏打字回复**，答完自动接着刚才的位置继续讲商品！

## 停止与自测

```bash
# 停止并清理容器
docker compose down

# 运行 6 项全链路自测
docker compose run --rm douyin python test_verify.py
```
