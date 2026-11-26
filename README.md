# douyin-barrage-mini（抖音 AI 直播助播导播台 · 跨平台架构版）

基于 **FastAPI 后端 + 独立 `web/` 导播台中控页 + Playwright CDP + Protobuf 解包 + 在线大模型 + `edge-tts` 跨平台前端语音输出** 构建，支持 macOS 与 Windows 跨平台演进。

## 核心特性

1. **可视化导播台中控页 (`http://127.0.0.1:8889`)**：
   - 在线输入网址随时**连接/切换/断开直播间**（免改配置重启）；
   - **一键开始/暂停循环讲品**、**当前朗读句高亮**、点任意一句**「▶ 从此句播」**；
   - 页面直接**喂入商品链接自动抓参数写口播稿**，在线编辑 `pitch.txt` 与 `knowledge.txt` 即时热生效；
   - **实时弹幕与 AI 动作监控流** + 底部**导播手动语音插播 / 公屏发弹幕**。
2. **前端跨平台统一发声**：无需依赖系统专属命令，浏览器（或未来桌面端 WebView 窗口）直接播放 TTS 语音，Mac 与 Windows 通用。
3. **界面化设置中心 (`config.json`)**：右上角「⚙️ 系统设置」在线配置大模型 API Key（界面自动脱敏打星号）、冷却时间与违禁词，首次自动继承 `.env`。
4. **跨平台浏览器启动器 (`launch_browser.py`)**：纯 Python 标准库自动识别 **macOS / Windows**，自动唤起本机 Chrome 或系统预装的 Microsoft Edge。

## 快速上手（2 步开播）

### 第 1 步：在本机打开独立助播浏览器窗口（Mac / Windows 通用）
在**终端 1** 运行（弹出独立浏览器窗口，首次扫码登录助播小号后永久保存）：

```bash
cd ~/douyin-barrage-mini
python3 launch_browser.py
# （Mac 上也可继续运行 bash start_mac_chrome.sh）
```

### 第 2 步：启动导播台后端并打开网页
在**终端 2** 运行：

```bash
cd ~/douyin-barrage-mini
docker compose up --build
```

然后在浏览器打开：**http://127.0.0.1:8889**
1. 点击页面右上角橙色按钮 **「🔇 激活声音输出」**；
2. 确认顶部直播间地址后点 **「🔌 连接/切换」**；
3. 点 **「▶️ 开始循环讲品」** 即可开始自动讲品 + 弹幕双通道（语音插播 + 公屏打字）答疑！

## 停止与 7 项全链路自测

```bash
# 停止并清理容器
docker compose down

# 运行 7 项全链路自动化自测
docker compose run --rm douyin python test_verify.py
```
