let ws = null;
let audioUnlocked = false;
let latestState = null;
let editorsLoaded = false;

const audioEl = document.getElementById("ttsPlayer");

audioEl.onended = () => notifyAudioEnded();
audioEl.onerror = () => notifyAudioEnded();

function notifyAudioEnded() {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ event: "audio_ended" }));
  }
}

function unlockAudio() {
  const Ctx = window.AudioContext || window.webkitAudioContext;
  if (Ctx) {
    const ctx = new Ctx();
    ctx.resume();
  }
  audioEl.src =
    "data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAEA";
  audioEl.play().catch(() => {});
  audioUnlocked = true;

  const btn = document.getElementById("unlockAudioBtn");
  btn.textContent = "🔊 声音已激活（跨平台输出中）";
  btn.className = "btn success";
}

function switchTab(name) {
  document.querySelectorAll(".tab").forEach((b) => {
    b.classList.toggle("active", b.dataset.tab === name);
  });
  ["director", "pitch", "knowledge"].forEach((t) => {
    document
      .getElementById(`tab-${t}`)
      .classList.toggle("hidden", t !== name);
  });
}

function renderPitchList(lines, activeIndex) {
  const box = document.getElementById("pitchList");
  box.innerHTML = "";
  if (!lines || lines.length === 0) {
    box.innerHTML = `<div class="muted">暂无口播稿，请在上方输入商品链接生成，或切到编辑标签添加。</div>`;
    return;
  }
  lines.forEach((line, idx) => {
    const row = document.createElement("div");
    row.className = "pitch-item" + (idx === activeIndex ? " active" : "");
    row.innerHTML = `
      <div style="display:flex;gap:10px;align-items:flex-start;">
        <span class="pitch-no">#${idx + 1}</span>
        <span>${escapeHtml(line)}</span>
      </div>
      <button class="btn ghost" style="padding:5px 10px;font-size:12px;" onclick="jumpPitch(${idx})">
        ▶ 从此句播
      </button>
    `;
    box.appendChild(row);
    if (idx === activeIndex) {
      row.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  });
}

function appendEvent(ev) {
  const feed = document.getElementById("eventFeed");
  const div = document.createElement("div");
  div.className = "ev-row";

  const labelMap = {
    chat: "💬 弹幕",
    gift: "🎁 送礼",
    like: "❤️ 点赞",
    follow: "➕ 关注",
    member: "👋 进房",
    stats: "🔥 在线",
    voice_qa: "🔊 语音插播",
    text_reply: "⌨️ 公屏回复",
    system: "系统",
    error: "异常",
  };
  const tagLabel = labelMap[ev.kind] || ev.kind;
  const detailText = ev.detail ? `：${escapeHtml(ev.detail)}` : "";
  div.innerHTML = `
    <span class="muted">[${ev.ts || ""}]</span>
    <span class="ev-tag ${ev.kind}">${tagLabel}</span>
    <strong>${escapeHtml(ev.title || "")}</strong>${detailText}
  `;
  feed.prepend(div);
  while (feed.children.length > 100) {
    feed.removeChild(feed.lastChild);
  }
}

function escapeHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function applyState(s) {
  latestState = s;
  const cfg = s.config || {};

  // 房间状态徽章
  const roomBadge = document.getElementById("roomBadge");
  const statusLabels = {
    idle: "未连接直播间",
    connecting: "正在打开直播间...",
    connected: "🟢 正在监听直播间",
    error: "🔴 连接失败",
  };
  roomBadge.className = `room-badge ${s.room_status || "idle"}`;
  roomBadge.textContent = statusLabels[s.room_status] || s.room_status;

  const errBanner = document.getElementById("errorBanner");
  if (s.room_status === "error" && s.room_error) {
    errBanner.textContent = "⚠️ " + s.room_error;
    errBanner.classList.remove("hidden");
  } else {
    errBanner.classList.add("hidden");
  }

  const urlInput = document.getElementById("liveUrlInput");
  if (!urlInput.value && cfg.live_url) {
    urlInput.value = cfg.live_url;
  }

  // 音色下拉框
  const voiceSel = document.getElementById("voiceSelect");
  if (voiceSel.options.length === 0 && s.voices) {
    s.voices.forEach((v) => {
      const opt = document.createElement("option");
      opt.value = v.id;
      opt.textContent = v.label;
      voiceSel.appendChild(opt);
    });
  }
  if (cfg.tts_voice) voiceSel.value = cfg.tts_voice;
  if (cfg.tts_rate) document.getElementById("rateSelect").value = cfg.tts_rate;

  // 开关状态
  document.getElementById("aiEnabledToggle").checked = !!cfg.ai_enabled;
  document.getElementById("voiceQaToggle").checked = !!cfg.voice_qa_enabled;
  document.getElementById("textReplyToggle").checked = !!cfg.text_reply_enabled;
  document.getElementById("dryRunToggle").checked = !!cfg.dry_run;

  const speakingPitch = !!(cfg.voice_enabled && cfg.voice_pitch_enabled);
  document.getElementById("startPitchBtn").disabled = speakingPitch;
  document.getElementById("pausePitchBtn").disabled = !speakingPitch;
  document.getElementById("qaQueueCount").textContent = s.qa_queue_size || 0;

  renderPitchList(s.pitch_lines || [], s.active_pitch_index);

  if (!editorsLoaded) {
    document.getElementById("pitchEditor").value = s.pitch_raw || "";
    document.getElementById("knowledgeEditor").value = s.knowledge || "";
    editorsLoaded = true;
  }
}

function connectWS() {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  ws = new WebSocket(`${proto}//${location.host}/ws`);

  ws.onopen = () => {
    document.getElementById("wsDot").className = "dot online";
    document.getElementById("wsStatusText").textContent = "后台实时已连接";
  };

  ws.onclose = () => {
    document.getElementById("wsDot").className = "dot";
    document.getElementById("wsStatusText").textContent = "连接断开，重连中...";
    setTimeout(connectWS, 2000);
  };

  ws.onmessage = (ev) => {
    const data = JSON.parse(ev.data);
    if (data.type === "state") {
      if (Array.isArray(data.recent_events)) {
        document.getElementById("eventFeed").innerHTML = "";
        data.recent_events.forEach((item) => appendEvent(item));
      }
      applyState(data);
    } else if (data.type === "event") {
      appendEvent(data);
    } else if (data.type === "speak") {
      document.getElementById("qaQueueCount").textContent =
        data.qa_queue_size || 0;
      if (latestState) {
        renderPitchList(latestState.pitch_lines || [], data.active_pitch_index);
      }
      const card = document.getElementById("nowSpeakingCard");
      const badge = document.getElementById("speakingBadge");
      if (data.kind === "qa") {
        card.className = "speaking-card qa";
        badge.className = "badge qa";
        badge.textContent = `🔥 语音插播答疑 · @${data.meta.nickname}`;
      } else {
        card.className = "speaking-card";
        badge.className = "badge";
        badge.textContent = `📢 循环讲品 (${data.meta.line_no}/${data.meta.total_lines})`;
      }
      document.getElementById("speakingText").textContent = data.text;

      if (audioUnlocked) {
        audioEl.src = "data:audio/mp3;base64," + data.audio_b64;
        audioEl.play().catch(() => {
          notifyAudioEnded();
        });
      } else {
        // 若用户未点激活声音，提示并延迟释放锁避免阻塞队列
        document.getElementById("speakingText").textContent =
          "⚠️ [尚未点击右上角激活声音] " + data.text;
        setTimeout(() => notifyAudioEnded(), 1200);
      }
    }
  };
}

async function apiPost(url, body = {}) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || data.error || "请求失败");
  }
  return data;
}

async function connectRoom() {
  const live_url = document.getElementById("liveUrlInput").value.trim();
  try {
    await apiPost("/api/room/connect", { live_url });
  } catch (e) {
    alert(e.message);
  }
}

async function disconnectRoom() {
  await apiPost("/api/room/disconnect");
}

async function voiceAction(action) {
  if (action === "start_pitch" && !audioUnlocked) {
    unlockAudio();
  }
  await apiPost("/api/voice/control", { action });
}

async function jumpPitch(index) {
  if (!audioUnlocked) unlockAudio();
  await apiPost("/api/voice/control", { action: "jump_pitch", index });
}

async function quickSaveToggles() {
  await apiPost("/api/config", {
    ai_enabled: document.getElementById("aiEnabledToggle").checked,
    voice_qa_enabled: document.getElementById("voiceQaToggle").checked,
    text_reply_enabled: document.getElementById("textReplyToggle").checked,
    dry_run: document.getElementById("dryRunToggle").checked,
    tts_voice: document.getElementById("voiceSelect").value,
    tts_rate: document.getElementById("rateSelect").value,
  });
}

async function generateScript() {
  const btn = document.getElementById("genScriptBtn");
  const statusEl = document.getElementById("genStatusText");
  btn.disabled = true;
  statusEl.textContent = "正在提取商品信息并请求 AI 生成口播稿，请稍候 (约 5~12 秒)...";
  try {
    const data = await apiPost("/api/script/generate", {
      product_url: document.getElementById("productUrlInput").value,
      extra_notes: document.getElementById("extraNotesInput").value,
    });
    const newPitch = `# 商品口播讲解稿：${data.product_title}\n` + (data.pitch_lines || []).join("\n");
    document.getElementById("pitchEditor").value = newPitch;

    let newKnowledge = document.getElementById("knowledgeEditor").value.trim();
    if (data.qa_entry && !newKnowledge.includes(data.qa_entry)) {
      newKnowledge += "\n" + data.qa_entry;
      document.getElementById("knowledgeEditor").value = newKnowledge;
    }

    await apiPost("/api/script/save", {
      pitch_raw: newPitch,
      knowledge: newKnowledge,
    });
    statusEl.textContent = `✅ 已生成并应用「${data.product_title}」共 ${(data.pitch_lines || []).length} 句口播稿！`;
  } catch (e) {
    statusEl.textContent = "❌ " + e.message;
  } finally {
    btn.disabled = false;
  }
}

async function saveScripts() {
  const pitch_raw = document.getElementById("pitchEditor").value;
  const knowledge = document.getElementById("knowledgeEditor").value;
  const data = await apiPost("/api/script/save", { pitch_raw, knowledge });
  const msg = `✅ 已保存热生效（共 ${data.line_count} 句口播词）`;
  document.getElementById("savePitchHint").textContent = msg;
  document.getElementById("saveKnowledgeHint").textContent = msg;
  setTimeout(() => {
    document.getElementById("savePitchHint").textContent = "";
    document.getElementById("saveKnowledgeHint").textContent = "";
  }, 3000);
}

async function manualInterject(action) {
  const input = document.getElementById("manualInput");
  const text = input.value.trim();
  if (!text) return;
  if (action === "interject_voice" && !audioUnlocked) {
    unlockAudio();
  }
  try {
    await apiPost("/api/voice/control", { action, text });
    input.value = "";
  } catch (e) {
    alert(e.message);
  }
}

function openSettings() {
  if (!latestState || !latestState.config) return;
  const cfg = latestState.config;
  document.getElementById("cfgBaseUrl").value = cfg.llm_base_url || "";
  document.getElementById("cfgApiKey").value = "";
  document.getElementById("apiKeyHint").textContent = cfg.has_api_key
    ? `当前已配置 (${cfg.llm_api_key_masked})`
    : "尚未配置密钥";
  document.getElementById("cfgModel").value = cfg.llm_model || "";
  document.getElementById("cfgBotNick").value = cfg.bot_nickname || "";
  document.getElementById("cfgCooldown").value = cfg.reply_cooldown || 12;
  document.getElementById("cfgCdpUrl").value = cfg.cdp_url || "";
  document.getElementById("cfgBannedWords").value = cfg.banned_words || "";
  document.getElementById("cfgOnlyChat").checked = !!cfg.only_chat;

  document.getElementById("settingsModal").classList.remove("hidden");
}

function closeSettings() {
  document.getElementById("settingsModal").classList.add("hidden");
}

async function saveSettingsModal() {
  const patch = {
    llm_base_url: document.getElementById("cfgBaseUrl").value.trim(),
    llm_api_key: document.getElementById("cfgApiKey").value.trim(),
    llm_model: document.getElementById("cfgModel").value.trim(),
    bot_nickname: document.getElementById("cfgBotNick").value.trim(),
    reply_cooldown: Number(document.getElementById("cfgCooldown").value || 12),
    cdp_url: document.getElementById("cfgCdpUrl").value.trim(),
    banned_words: document.getElementById("cfgBannedWords").value.trim(),
    only_chat: document.getElementById("cfgOnlyChat").checked,
  };
  await apiPost("/api/config", patch);
  closeSettings();
}

connectWS();
