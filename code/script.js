
"use strict";

const $ = id => document.getElementById(id);
const ICON = "https://i.pinimg.com/736x/78/8f/4a/788f4aac6662168309239d653f205979.jpg";

const STORAGE = {
  url: "mh2_pc_assistant_database_url",
  token: "mh2_pc_assistant_auth_token",
  messages: "mh2_pc_assistant_chat_history"
};

const state = {
  databaseUrl: localStorage.getItem(STORAGE.url) || "",
  authToken: localStorage.getItem(STORAGE.token) || "",
  messages: [],
  sending: false,
  recognition: null,
  recognitionBusy: false,
  recording: false,
  voiceSupported: false,
  micPermissionDenied: false,
  callActive: false,
  callConnecting: false,
  callConnected: false,
  muted: false,
  speakerMode: false,
  callStartedAt: 0,
  callTimer: null,
  connectTimer: null,
  pollers: new Map(),
  awaitingPcResponse: false,
  waitingForConfirmation: false,
  pendingDangerousAction: null,
  lastCommand: "",
  audioContext: null,
  ringOscillators: [],
  ringLoopTimer: null,
  recordingStream: null,
  mediaRecorder: null,
  recordingChunks: [],
  recordedBlob: null,
  callGeneration: 0,
  speechGeneration: 0,
  recognitionGeneration: 0,
  listenTimer: null,
  speechPromiseResolve: null,
  activeCommandCount: 0,
  typingMode: false,
  typingText: "",
  typingTarget: "",
  lastCommandId: ""
};

try {
  const history = JSON.parse(localStorage.getItem(STORAGE.messages) || "[]");
  if (Array.isArray(history)) state.messages = history.slice(-100);
} catch {
  state.messages = [];
}

function toast(message) {
  const element = $("toast");
  if (!element) {
    console.log(message);
    return;
  }

  element.textContent = message;
  element.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => element.classList.remove("show"), 2800);
}

function escapeHTML(value) {
  return String(value).replace(/[&<>"']/g, ch => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  })[ch]);
}

function saveHistory() {
  try {
    localStorage.setItem(
      STORAGE.messages,
      JSON.stringify(state.messages.slice(-100))
    );
  } catch {
    toast("Could not save chat history.");
  }
}

function timeLabel(timestamp) {
  return new Date(timestamp).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit"
  });
}

function makeAvatar(role) {
  return role === "user"
    ? '<img class="avatar" src="' + ICON + '" alt="You">'
    : '<div class="avatar bot-avatar">✦</div>';
}

function renderMessage(message) {
  if (!$("messages")) return;

  const row = document.createElement("div");
  row.className = "message-row " +
    (message.role === "user" ? "user" : "bot");
  row.dataset.messageId = message.id;

  const labels = {
    queued: "Waiting for PC agent",
    sent: "Sent to Firebase",
    processing: "PC is processing",
    completed: "Completed",
    error: "Failed"
  };

  row.innerHTML =
    makeAvatar(message.role) +
    '<div class="message-content">' +
      '<div class="message-label">' +
        (message.role === "user" ? "You" : "MH2 Assistant") +
      '</div>' +
      '<div class="bubble">' + escapeHTML(message.text) + '</div>' +
      '<div class="meta">' + timeLabel(message.timestamp) + '</div>' +
      (message.status
        ? '<div class="msg-status">' +
            escapeHTML(labels[message.status] || message.status) +
          '</div>'
        : "") +
    '</div>';

  $("messages").appendChild(row);
}

function renderAll() {
  if (!$("messages")) return;

  $("messages").replaceChildren();

  if ($("welcome")) {
    $("welcome").style.display = state.messages.length ? "none" : "";
  }

  state.messages.forEach(renderMessage);
  scrollBottom();
}

function scrollBottom() {
  requestAnimationFrame(() => {
    if ($("chat")) $("chat").scrollTop = $("chat").scrollHeight;
  });
}

function addMessage(role, text, extra = {}) {
  const message = {
    id: crypto.randomUUID
      ? crypto.randomUUID()
      : Date.now() + "-" + Math.random(),
    role,
    text: String(text),
    timestamp: Date.now(),
    ...extra
  };

  state.messages.push(message);
  state.messages = state.messages.slice(-100);
  saveHistory();

  if ($("welcome")) $("welcome").style.display = "none";
  renderMessage(message);
  scrollBottom();

  return message;
}

function updateMessage(id, changes) {
  const message = state.messages.find(item => item.id === id);
  if (!message) return;

  Object.assign(message, changes);
  saveHistory();

  const old = $("messages")?.querySelector(
    '[data-message-id="' + CSS.escape(id) + '"]'
  );

  if (!old) return;

  const temp = document.createElement("div");
  temp.className = "message-row " +
    (message.role === "user" ? "user" : "bot");
  temp.dataset.messageId = message.id;

  const labels = {
    queued: "Waiting for PC agent",
    sent: "Sent to Firebase",
    processing: "PC is processing",
    completed: "Completed",
    error: "Failed"
  };

  temp.innerHTML =
    makeAvatar(message.role) +
    '<div class="message-content">' +
      '<div class="message-label">' +
        (message.role === "user" ? "You" : "MH2 Assistant") +
      '</div>' +
      '<div class="bubble">' + escapeHTML(message.text) + '</div>' +
      '<div class="meta">' + timeLabel(message.timestamp) + '</div>' +
      (message.status
        ? '<div class="msg-status">' +
            escapeHTML(labels[message.status] || message.status) +
          '</div>'
        : "") +
    '</div>';

  old.replaceWith(temp);
}

function databaseEndpoint(path) {
  if (!state.databaseUrl) {
    throw new Error("Configure Firebase in Settings first.");
  }

  const base = state.databaseUrl.trim().replace(/\/+$/, "");

  if (!/^https:\/\/[a-zA-Z0-9.-]+(?::\d+)?$/.test(base)) {
    throw new Error("Enter a valid HTTPS Firebase Database URL.");
  }

  let url = base + "/" +
    path.replace(/^\/+/, "").replace(/\/+$/, "") + ".json";

  if (state.authToken) {
    url += "?auth=" + encodeURIComponent(state.authToken);
  }

  return url;
}

async function databaseRequest(path, options = {}) {
  const response = await fetch(databaseEndpoint(path), {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    },
    cache: "no-store"
  });

  const raw = await response.text();
  let data = null;

  try {
    data = raw ? JSON.parse(raw) : null;
  } catch {
    data = raw;
  }

  if (!response.ok) {
    throw new Error(
      data && typeof data === "object" && data.error
        ? data.error
        : "Firebase HTTP " + response.status
    );
  }

  if (data && typeof data === "object" && data.error) {
    throw new Error(data.error);
  }

  return data;
}

function updateConnection(text, mode = "") {
  if ($("connectionText")) {
    $("connectionText").textContent = "● " + (
      text ||
      (state.databaseUrl
        ? "Firebase configured"
        : "Firebase not configured")
    );

    $("connectionText").style.color =
      mode === "error" ? "#ef6464" :
      mode === "connected" ? "var(--green)" :
      "var(--muted)";
  }

  if ($("headerStatus")) {
    $("headerStatus").textContent = state.callActive
      ? state.callConnected ? "Voice session active" : "Connecting..."
      : state.databaseUrl ? "Firebase configured" : "Voice & PC Control";
  }
}

function updateCallTranscript(text) {
  if ($("callTranscript")) $("callTranscript").textContent = text;
}

function setCallSubtitle(text) {
  if ($("callSubtitle")) $("callSubtitle").textContent = text;
  if ($("callStatus")) $("callStatus").textContent = text;
}

function startCallTimer() {
  clearInterval(state.callTimer);
  state.callStartedAt = Date.now();

  if ($("callTimer")) $("callTimer").textContent = "00:00";

  state.callTimer = setInterval(() => {
    if (!state.callActive || !state.callConnected) return;

    const elapsed = Math.floor(
      (Date.now() - state.callStartedAt) / 1000
    );

    if ($("callTimer")) {
      $("callTimer").textContent =
        String(Math.floor(elapsed / 60)).padStart(2, "0") + ":" +
        String(elapsed % 60).padStart(2, "0");
    }
  }, 1000);
}

function cancelListenRestart() {
  clearTimeout(state.listenTimer);
  state.listenTimer = null;
}

function stopSpeech() {
  state.speechGeneration++;

  if ("speechSynthesis" in window) {
    window.speechSynthesis.cancel();
  }

  if (state.speechPromiseResolve) {
    const resolve = state.speechPromiseResolve;
    state.speechPromiseResolve = null;
    resolve(false);
  }
}

function speak(text) {
  if (
    !("speechSynthesis" in window) ||
    state.muted ||
    !state.callActive ||
    !state.callConnected ||
    !String(text).trim()
  ) {
    return Promise.resolve(false);
  }

  stopSpeech();

  const generation = state.callGeneration;
  const speechId = state.speechGeneration;
  const utterance = new SpeechSynthesisUtterance(String(text));

  utterance.lang = "en-US";
  utterance.rate = 0.96;
  utterance.pitch = 1.02;

  return new Promise(resolve => {
    let settled = false;
    let watchdog;

    const finish = result => {
      if (settled) return;
      settled = true;
      clearTimeout(watchdog);

      if (state.speechPromiseResolve === finish) {
        state.speechPromiseResolve = null;
      }

      resolve(result);
    };

    state.speechPromiseResolve = finish;

    watchdog = setTimeout(
      () => finish(false),
      Math.max(20000, String(text).length * 250)
    );

    utterance.onstart = () => {
      if (
        generation !== state.callGeneration ||
        speechId !== state.speechGeneration ||
        !state.callActive
      ) {
        finish(false);
        return;
      }

      setCallSubtitle("MH2 is speaking...");
      $("callScreen")?.classList.remove("listening");
    };

    utterance.onend = () => {
      if (
        generation !== state.callGeneration ||
        speechId !== state.speechGeneration
      ) {
        finish(false);
        return;
      }

      if (state.callActive && state.callConnected && !state.muted) {
        setCallSubtitle("Ready for your next command");
      }

      finish(true);
    };

    utterance.onerror = () => finish(false);

    try {
      window.speechSynthesis.speak(utterance);
    } catch {
      finish(false);
    }
  });
}

function resumeCallListening(delay = 700) {
  cancelListenRestart();

  if (
    !state.callActive ||
    !state.callConnected ||
    state.muted ||
    state.awaitingPcResponse ||
    state.micPermissionDenied
  ) return;

  const generation = state.callGeneration;

  state.listenTimer = setTimeout(() => {
    state.listenTimer = null;

    if (
      generation !== state.callGeneration ||
      !state.callActive ||
      !state.callConnected ||
      state.muted ||
      state.awaitingPcResponse ||
      state.micPermissionDenied
    ) return;

    if ("speechSynthesis" in window && window.speechSynthesis.speaking) {
      resumeCallListening(500);
      return;
    }

    startListening(true);
  }, delay);
}

function startListening(silent = false) {
  if (!state.callActive || !state.callConnected) {
    if (!silent) toast("Wait until the call connects.");
    return;
  }

  if (state.muted) {
    if (!silent) toast("Unmute the microphone first.");
    return;
  }

  if (state.awaitingPcResponse) {
    if (!silent) toast("Wait for the current PC command.");
    return;
  }

  if (state.micPermissionDenied) {
    if (!silent) toast("Allow microphone access in browser settings.");
    return;
  }

  if (!state.recognition) {
    if (!silent) toast("Voice recognition is unavailable.");
    return;
  }

  if (state.recognitionBusy) return;

  if ("speechSynthesis" in window && window.speechSynthesis.speaking) {
    resumeCallListening(600);
    return;
  }

  cancelListenRestart();

  try {
    state.recognitionGeneration++;
    state.recognition.start();
  } catch (error) {
    console.warn(error);
    resumeCallListening(1200);

    if (!silent) toast("Microphone is busy. Try again shortly.");
  }
}

async function startRinging() {
  stopRinging();

  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextClass) return;

  try {
    if (!state.audioContext || state.audioContext.state === "closed") {
      state.audioContext = new AudioContextClass();
    }

    await state.audioContext.resume();

    if (!state.callActive || state.callConnected) return;

    const ctx = state.audioContext;

    const ringOnce = () => {
      if (
        !state.callActive ||
        state.callConnected ||
        ctx.state === "closed"
      ) return;

      const start = ctx.currentTime;
      const gain = ctx.createGain();

      gain.gain.setValueAtTime(0.0001, start);
      gain.gain.linearRampToValueAtTime(0.06, start + 0.04);
      gain.gain.setValueAtTime(0.06, start + 0.42);
      gain.gain.linearRampToValueAtTime(0.0001, start + 0.52);
      gain.gain.setValueAtTime(0.0001, start + 0.62);
      gain.gain.linearRampToValueAtTime(0.06, start + 0.66);
      gain.gain.setValueAtTime(0.06, start + 1.04);
      gain.gain.linearRampToValueAtTime(0.0001, start + 1.14);
      gain.connect(ctx.destination);

      [440, 480].forEach(freq => {
        const osc = ctx.createOscillator();
        osc.type = "sine";
        osc.frequency.value = freq;
        osc.connect(gain);
        osc.start(start);
        osc.stop(start + 1.16);
        state.ringOscillators.push(osc);

        osc.onended = () => {
          try { osc.disconnect(); } catch {}
          state.ringOscillators =
            state.ringOscillators.filter(item => item !== osc);
        };
      });
    };

    ringOnce();
    state.ringLoopTimer = setInterval(ringOnce, 3000);
  } catch (error) {
    console.warn(error);
  }
}

function stopRinging() {
  clearInterval(state.ringLoopTimer);
  state.ringLoopTimer = null;

  state.ringOscillators.forEach(osc => {
    try { osc.stop(); } catch {}
    try { osc.disconnect(); } catch {}
  });

  state.ringOscillators = [];
}

function showCallScreen() {
  $("callScreen")?.classList.add("open");
  $("callScreen")?.setAttribute("aria-hidden", "false");
  $("startCallBtn")?.classList.add("calling");
}

function hideCallScreen() {
  $("callScreen")?.classList.remove("open", "listening");
  $("callScreen")?.setAttribute("aria-hidden", "true");
  $("startCallBtn")?.classList.remove("calling");
}

async function startCall() {
  if (state.callActive) return;

  if (!state.voiceSupported) {
    toast("Voice recognition is not supported. Try Chrome or Edge.");
    return;
  }

  if (!state.databaseUrl) {
    openSettings();
    toast("Configure Firebase before starting a voice session.");
    return;
  }

  cancelListenRestart();
  stopSpeech();

  state.callGeneration++;
  state.callActive = true;
  state.callConnecting = true;
  state.callConnected = false;
  state.muted = false;
  state.speakerMode = false;
  state.awaitingPcResponse = false;
  state.waitingForConfirmation = false;
  state.pendingDangerousAction = null;
  state.micPermissionDenied = false;

  showCallScreen();

  $("callAvatarWrap")?.classList.add("active");
  $("callMuteBtn")?.classList.remove("active");
  $("callSpeakerBtn")?.classList.remove("active");
  $("callDialBtn")?.classList.remove("active");
  $("callRecordBtn")?.classList.remove("active");
  $("dialpad")?.classList.remove("open");

  $("callMuteBtn")?.setAttribute("aria-pressed", "false");
  $("callSpeakerBtn")?.setAttribute("aria-pressed", "false");
  $("callDialBtn")?.setAttribute("aria-pressed", "false");

  if ($("muteLabel")) $("muteLabel").textContent = "Mute";
  if ($("speakerLabel")) $("speakerLabel").textContent = "Speaker";
  if ($("callTimer")) $("callTimer").textContent = "00:00";

  updateCallTranscript("Calling MH2 PC Assistant...");
  setCallSubtitle("Connecting...");
  updateConnection("Voice session connecting");
  startRinging();

  const generation = state.callGeneration;

  state.connectTimer = setTimeout(async () => {
    if (!state.callActive || generation !== state.callGeneration) return;

    stopRinging();
    state.callConnecting = false;
    state.callConnected = true;

    startCallTimer();
    setCallSubtitle("Connected · Local voice session");
    updateCallTranscript("MH2: Hello.");
    updateConnection("Voice session active", "connected");

    await speak("Hello. I am ready for your command.");

    if (
      state.callActive &&
      state.callConnected &&
      !state.muted &&
      generation === state.callGeneration
    ) {
      setCallSubtitle("Ready for your command");
      resumeCallListening(700);
    }
  }, 1500);
}

async function endCall() {
  if (!state.callActive) {
    hideCallScreen();
    return;
  }

  state.callGeneration++;
  state.callActive = false;
  state.callConnecting = false;
  state.callConnected = false;
  state.recording = false;
  state.recognitionBusy = false;
  state.muted = false;
  state.awaitingPcResponse = false;
  state.waitingForConfirmation = false;
  state.pendingDangerousAction = null;
  state.typingMode = false;
  state.typingText = "";

  cancelListenRestart();
  clearTimeout(state.connectTimer);
  state.connectTimer = null;

  stopRinging();
  stopSpeech();
  clearInterval(state.callTimer);
  state.callTimer = null;

  try { state.recognition?.abort(); } catch {}
  await stopRecording(false);

  $("callAvatarWrap")?.classList.remove("active");
  $("callMuteBtn")?.classList.remove("active");
  $("callSpeakerBtn")?.classList.remove("active");
  $("callRecordBtn")?.classList.remove("active");
  $("micBtn")?.classList.remove("recording");
  $("recordingIndicator")?.classList.remove("active");

  if ($("recordLabel")) $("recordLabel").textContent = "Record";
  if ($("muteLabel")) $("muteLabel").textContent = "Mute";

  $("callMuteBtn")?.setAttribute("aria-pressed", "false");
  $("callSpeakerBtn")?.setAttribute("aria-pressed", "false");

  hideCallScreen();
  updateConnection(
    state.databaseUrl ? "Firebase configured" : "Firebase not configured"
  );

  toast("Call ended.");
}

function setupRecognition() {
  const SpeechRecognition =
    window.SpeechRecognition || window.webkitSpeechRecognition;

  if (!SpeechRecognition) {
    state.voiceSupported = false;

    if ($("micBtn")) {
      $("micBtn").disabled = true;
      $("micBtn").title = "Use Chrome or Edge for voice recognition";
    }

    return;
  }

  state.voiceSupported = true;

  const recognition = new SpeechRecognition();
  recognition.lang = "en-US";
  recognition.continuous = false;
  recognition.interimResults = true;
  recognition.maxAlternatives = 1;
  state.recognition = recognition;

  recognition.onstart = () => {
    state.recording = true;
    state.recognitionBusy = true;
    state.micPermissionDenied = false;

    $("micBtn")?.classList.add("recording");

    if (state.callActive && state.callConnected) {
      $("callScreen")?.classList.add("listening");
      setCallSubtitle("Listening...");
    } else if (!state.callActive) {
      toast("Listening...");
    }
  };

  recognition.onresult = event => {
    let finalText = "";
    let interimText = "";

    for (let i = event.resultIndex; i < event.results.length; i++) {
      const transcript = event.results[i][0].transcript;

      if (event.results[i].isFinal) finalText += transcript;
      else interimText += transcript;
    }

    if (state.callActive) {
      updateCallTranscript(
        finalText ? "You: " + finalText : "You: " + interimText
      );
    } else if ($("messageInput")) {
      $("messageInput").value = finalText || interimText;
      resizeInput();
    }

    if (!finalText.trim()) return;

    const command = finalText.trim();

    if (state.callActive) {
      handleVoiceCommand(command);
    } else {
      sendCommand(command, "voice");
    }

    try { recognition.stop(); } catch {}
  };

  recognition.onerror = event => {
    console.warn("Speech recognition error:", event.error);

    if (
      event.error === "not-allowed" ||
      event.error === "service-not-allowed"
    ) {
      state.micPermissionDenied = true;

      if (state.callActive) {
        setCallSubtitle("Microphone permission denied");
      }

      toast("Allow microphone access in browser settings.");
      return;
    }

    if (event.error === "audio-capture") {
      if (state.callActive) setCallSubtitle("No microphone detected");
      toast("Check that your microphone is connected.");
      return;
    }

    if (event.error === "network") {
      if (state.callActive) {
        setCallSubtitle("Voice service unavailable. Retrying...");
        resumeCallListening(2500);
      }
      return;
    }

    if (
      event.error !== "aborted" &&
      event.error !== "no-speech" &&
      state.callActive
    ) {
      setCallSubtitle("Voice error. Retrying...");
    }
  };

  recognition.onend = () => {
    state.recording = false;
    state.recognitionBusy = false;

    $("micBtn")?.classList.remove("recording");
    $("callScreen")?.classList.remove("listening");

    if (
      state.callActive &&
      state.callConnected &&
      !state.muted &&
      !state.awaitingPcResponse &&
      !state.micPermissionDenied
    ) {
      resumeCallListening(700);
    }
  };
}

/* General voice command parser */

function normalizeCommand(command) {
  return String(command || "")
    .toLowerCase()
    .trim()
    .replace(/[.!?,]+$/g, "")
    .replace(/\s+/g, " ");
}

function parseTypingCommand(command) {
  const text = String(command).trim();
  const lower = normalizeCommand(text);

  if (/^(type end|typing end|stop typing|finish typing|typing stop|type stop)$/.test(lower)) {
    return { action: "type_end" };
  }

  if (/^(send message|send it|send now|press enter|submit message)$/.test(lower)) {
    return { action: "type_send" };
  }

  if (/^(type now|start typing|begin typing|typing start)$/.test(lower)) {
    return { action: "type_start" };
  }

  const targetMatch = text.match(
    /^(?:type in|typing in|start typing in|type into)\s+(.+)$/i
  );

  if (targetMatch) {
    return {
      action: "type_target",
      target: targetMatch[1].trim()
    };
  }

  const typeMatch = text.match(/^(?:type|write|enter text)\s+(.+)$/i);

  if (typeMatch) {
    return {
      action: "type_text",
      text: typeMatch[1]
    };
  }

  return null;
}

function normalizeTargetName(target) {
  const t = normalizeCommand(target);

  if (/whatsapp|whats app/.test(t)) return "whatsapp";
  if (/word|microsoft word|ms word/.test(t)) return "word";
  if (/notepad|text editor/.test(t)) return "notepad";
  if (/browser|chrome|google chrome/.test(t)) return "chrome";
  if (/recycle bin|recyclebin/.test(t)) return "recycle_bin";
  if (/file manager|file explorer|explorer/.test(t)) return "file_manager";
  if (/desktop/.test(t)) return "desktop";
  if (/search box|search bar/.test(t)) return "search";
  if (/address bar|url bar/.test(t)) return "address_bar";

  return t;
}

function isTypingEnd(command) {
  return /^(type end|typing end|stop typing|finish typing|typing stop|type stop)$/i
    .test(normalizeCommand(command));
}

function handleTypingCommand(command) {
  const parsed = parseTypingCommand(command);

  if (!parsed) return false;

  if (parsed.action === "type_end") {
    state.typingMode = false;
    state.awaitingPcResponse = true;
    sendCommand("TYPE_END", "voice");
    return true;
  }

  if (parsed.action === "type_start") {
    state.typingMode = true;
    state.typingText = "";
    state.typingTarget = "";
    state.awaitingPcResponse = false;

    const message =
      "Typing mode started. Dictate your text. Say type end when finished.";

    updateCallTranscript("MH2: " + message);
    setCallSubtitle("Typing mode active");
    addMessage("assistant", message);
    speak(message);

    return true;
  }

  if (parsed.action === "type_target") {
    state.typingTarget = normalizeTargetName(parsed.target);
    state.typingMode = true;
    state.awaitingPcResponse = true;

    sendCommand("TYPE_TARGET " + state.typingTarget, "voice");
    return true;
  }

  if (parsed.action === "type_text") {
    if (!state.typingMode) {
      state.typingMode = true;
      state.typingText = "";
    }

    state.typingText +=
      (state.typingText ? " " : "") + parsed.text;

    state.awaitingPcResponse = true;
    sendCommand("TYPE_TEXT " + parsed.text, "voice");
    return true;
  }

  if (parsed.action === "type_send") {
    if (state.typingMode) {
      toast("Say 'type end' before sending.");
      return true;
    }

    state.awaitingPcResponse = true;
    sendCommand("TYPE_SEND", "voice");
    return true;
  }

  return false;
}

/*
  Send standardised commands to the Python agent.
  The Python agent must implement each action.
*/

function parseGeneralCommand(command) {
  const original = String(command || "").trim();
  const lower = normalizeCommand(original);

  if (!lower) return null;

  if (/^(open|show|launch|start)\s+(file manager|file explorer|windows explorer|explorer|my computer|this pc)$/.test(lower)) {
    return "OPEN_FILE_MANAGER";
  }

  if (/^(open|show|go to)\s+(c drive|drive c|local disk c|c:)$/.test(lower)) {
    return "OPEN_DRIVE C";
  }

  if (/^(open|show|go to)\s+(d drive|drive d|local disk d|d:)$/.test(lower)) {
    return "OPEN_DRIVE D";
  }

  if (/^(open|show|go to)\s+(e drive|drive e|local disk e|e:)$/.test(lower)) {
    return "OPEN_DRIVE E";
  }

  if (/^(open|show|go to)\s+(f drive|drive f|local disk f|f:)$/.test(lower)) {
    return "OPEN_DRIVE F";
  }

  if (/^(open|show|go to)\s+(recycle bin|recyclebin)$/.test(lower)) {
    return "OPEN_RECYCLE_BIN";
  }

  if (/^(open|show|go to)\s+(downloads|download folder)$/.test(lower)) {
    return "OPEN_FOLDER DOWNLOADS";
  }

  if (/^(open|show|go to)\s+(documents|document folder)$/.test(lower)) {
    return "OPEN_FOLDER DOCUMENTS";
  }

  if (/^(open|show|go to)\s+(pictures|images|photos|picture folder)$/.test(lower)) {
    return "OPEN_FOLDER PICTURES";
  }

  if (/^(open|show|go to)\s+(desktop|desktop folder)$/.test(lower)) {
    return "OPEN_FOLDER DESKTOP";
  }

  if (/^(select all|select every file|select all files)$/.test(lower)) {
    return "SELECT_ALL_FILES";
  }

  if (/^(select all images|select all pictures|select all photos)$/.test(lower)) {
    return "SELECT_ALL_IMAGES";
  }

  if (/^(deselect all|unselect all|clear selection)$/.test(lower)) {
    return "DESELECT_ALL";
  }

  if (/^(delete selected|delete selected files|remove selected files)$/.test(lower)) {
    return "DELETE_SELECTED_FILES_REQUEST";
  }

  if (/^(delete all files|delete everything|delete all images|delete all pictures)$/.test(lower)) {
    return "DELETE_ALL_FILES_REQUEST";
  }

  if (/^(empty recycle bin|clear recycle bin)$/.test(lower)) {
    return "EMPTY_RECYCLE_BIN_REQUEST";
  }

  if (/^(confirm delete|confirm deletion|yes delete)$/.test(lower)) {
    return "CONFIRM_DELETE";
  }

  if (/^(cancel action|cancel delete|cancel deletion|never mind)$/.test(lower)) {
    return "CANCEL_ACTION";
  }

  if (/^(open|launch|start)\s+chrome$/.test(lower)) {
    return "OPEN_APP CHROME";
  }

  if (/^(open|launch|start)\s+(whatsapp|whats app)$/.test(lower)) {
    return "OPEN_APP WHATSAPP";
  }

  if (/^(open|launch|start)\s+(word|microsoft word|ms word)$/.test(lower)) {
    return "OPEN_APP WORD";
  }

  if (/^(open|launch|start)\s+notepad$/.test(lower)) {
    return "OPEN_APP NOTEPAD";
  }

  if (/^(open|show)\s+whatsapp inbox$/.test(lower)) {
    return "OPEN_WHATSAPP_INBOX";
  }

  if (/^(open|show)\s+whatsapp contacts$/.test(lower)) {
    return "OPEN_WHATSAPP_CONTACTS";
  }

  if (/^(click|left click)$/.test(lower)) {
    return "MOUSE_CLICK";
  }

  if (/^(double click|double-click)$/.test(lower)) {
    return "MOUSE_DOUBLE_CLICK";
  }

  if (/^(right click|right-click)$/.test(lower)) {
    return "MOUSE_RIGHT_CLICK";
  }

  if (/^(scroll up|page up)$/.test(lower)) {
    return "MOUSE_SCROLL UP";
  }

  if (/^(scroll down|page down)$/.test(lower)) {
    return "MOUSE_SCROLL DOWN";
  }

  const moveMatch = lower.match(
    /^move mouse (left|right|up|down)(?:\s+(\d+))?$/
  );

  if (moveMatch) {
    const amount = Math.min(
      Math.max(Number(moveMatch[2] || 100), 1),
      2000
    );

    return "MOUSE_MOVE " + moveMatch[1].toUpperCase() + " " + amount;
  }

  const coordinateMatch = lower.match(
    /^move mouse to x\s*(\d+)\s*y\s*(\d+)$/
  );

  if (coordinateMatch) {
    return "MOUSE_MOVE_TO " +
      Math.min(Number(coordinateMatch[1]), 10000) + " " +
      Math.min(Number(coordinateMatch[2]), 10000);
  }

  if (/^(send message|send it|send now)$/.test(lower)) {
    return "SEND_MESSAGE";
  }

  /*
    Unknown commands remain natural-language instructions.
    The Python agent can decide whether it supports them.
  */
  return original;
}

function handleVoiceCommand(command) {
  if (
    !state.callActive ||
    !state.callConnected ||
    state.muted ||
    state.awaitingPcResponse
  ) return;

  const normalized = normalizeCommand(command);

  // In typing mode, only the stop-typing phrase is treated as a command.
  if (state.typingMode) {
    if (isTypingEnd(command)) {
      handleTypingCommand(command);
      return;
    }

    state.typingText +=
      (state.typingText ? " " : "") + String(command).trim();

    state.awaitingPcResponse = true;
    sendCommand("TYPE_TEXT " + String(command).trim(), "voice");
    return;
  }

  if (parseTypingCommand(command)) {
    if (handleTypingCommand(command)) return;
  }

  if (state.waitingForConfirmation) {
    if (/^(confirm delete|confirm deletion|yes delete)$/i.test(normalized)) {
      state.waitingForConfirmation = false;
      state.awaitingPcResponse = true;
      sendCommand("CONFIRM_DELETE", "voice");
      return;
    }

    if (/^(cancel action|cancel delete|cancel deletion|no|nope|never mind)$/i.test(normalized)) {
      state.waitingForConfirmation = false;
      state.pendingDangerousAction = null;
      state.awaitingPcResponse = true;
      sendCommand("CANCEL_ACTION", "voice");
      return;
    }

    const reminder = "Please say confirm delete to continue, or cancel action.";
    updateCallTranscript("MH2: " + reminder);
    setCallSubtitle("Waiting for confirmation");
    speak(reminder);
    return;
  }

  const mapped = parseGeneralCommand(command);

  if (mapped && (
    mapped === "DELETE_SELECTED_FILES_REQUEST" ||
    mapped === "DELETE_ALL_FILES_REQUEST" ||
    mapped === "EMPTY_RECYCLE_BIN_REQUEST"
  )) {
    state.waitingForConfirmation = true;
    state.pendingDangerousAction = mapped;

    const warning =
      "This action may delete files. Please review the selected files on your PC. " +
      "Say confirm delete to continue, or cancel action to stop.";

    updateCallTranscript("MH2: " + warning);
    setCallSubtitle("Waiting for deletion confirmation");
    addMessage("assistant", warning);
    speak(warning);

    // The Python agent must also enforce its own deletion confirmation.
    state.awaitingPcResponse = true;
    sendCommand(mapped, "voice");
    return;
  }

  state.awaitingPcResponse = true;
  cancelListenRestart();
  updateCallTranscript("You: " + command);
  setCallSubtitle("Sending command to your PC...");
  sendCommand(mapped || command, "voice");
}

async function sendCommand(textOverride, source = "text") {
  const text = String(
    typeof textOverride === "string"
      ? textOverride
      : $("messageInput")?.value || ""
  ).trim();

  if (!text) {
    if (source === "voice") {
      state.awaitingPcResponse = false;
      resumeCallListening();
    }
    return;
  }

  if (state.sending) {
    toast("Please wait for the current command to send.");

    if (source === "voice") {
      state.awaitingPcResponse = false;
      resumeCallListening(1000);
    }

    return;
  }

  if (!state.databaseUrl) {
    state.awaitingPcResponse = false;
    openSettings();
    toast("Configure Firebase first.");
    resumeCallListening(1200);
    return;
  }

  state.sending = true;
  state.activeCommandCount++;

  if ($("sendBtn")) $("sendBtn").disabled = true;

  if (
    source === "text" &&
    typeof textOverride !== "string" &&
    $("messageInput")
  ) {
    $("messageInput").value = "";
    resizeInput();
  }

  state.lastCommand = text;

  const message = addMessage("user", text, {
    status: "queued",
    source
  });

  if (state.callActive && state.callConnected) {
    state.awaitingPcResponse = true;
    updateCallTranscript("You: " + text);
    setCallSubtitle("Sending command to your PC...");
  }

  updateConnection("Sending command...");

  try {
    const payload = {
      command: text,
      text,
      source,
      status: "pending",
      response: null,
      createdAt: Date.now(),
      client: "MH2 PC Assistant",
      protocolVersion: 3
    };

    const result = await databaseRequest("commands", {
      method: "POST",
      body: JSON.stringify(payload)
    });

    if (!result || !result.name) {
      throw new Error("Firebase did not return a command ID.");
    }

    state.lastCommandId = result.name;

    updateMessage(message.id, {
      status: "sent",
      commandId: result.name
    });

    updateConnection("Command sent · Waiting for PC", "connected");

    if (!(state.callActive && state.callConnected)) {
      addMessage(
        "assistant",
        "Command sent to your PC. Waiting for the Python agent..."
      );
    }

    startPolling(message.id, result.name);
  } catch (error) {
    updateMessage(message.id, { status: "error" });
    updateConnection("Database request failed", "error");

    const failure = "I couldn't send that command. " + error.message;
    addMessage("assistant", failure);

    if (state.callActive && state.callConnected) {
      state.awaitingPcResponse = false;
      updateCallTranscript("MH2: " + failure);
      setCallSubtitle("Command could not be sent");
      await speak(failure);
      resumeCallListening(800);
    }

    toast(error.message);
  } finally {
    state.sending = false;
    state.activeCommandCount = Math.max(0, state.activeCommandCount - 1);

    if ($("sendBtn")) $("sendBtn").disabled = false;
    if (!state.callActive && $("messageInput")) {
      $("messageInput").focus();
    }
  }
}

function startPolling(messageId, commandId) {
  stopPolling(messageId);

  let attempts = 0;
  const maxAttempts = 300;
  let busy = false;

  const timer = setInterval(async () => {
    if (busy) return;
    busy = true;
    attempts++;

    try {
      if (attempts > maxAttempts) {
        stopPolling(messageId);

        const text =
          "I haven't received a response yet. Please check that your Python agent is running.";

        updateMessage(messageId, { status: "sent" });
        addMessage("assistant", text);

        if (state.callActive && state.callConnected) {
          state.awaitingPcResponse = false;
          updateCallTranscript("MH2: " + text);
          setCallSubtitle("No response from PC agent");
          await speak(text);
          resumeCallListening(800);
        }

        updateConnection("Command sent · No response yet", "connected");
        return;
      }

      const data = await databaseRequest("commands/" + commandId);
      if (!data) return;

      const status = String(data.status || "").toLowerCase();

      if (status === "processing") {
        updateMessage(messageId, { status: "processing" });
        return;
      }

      const responseText =
        typeof data.response === "string" ? data.response :
        data.response && typeof data.response.text === "string"
          ? data.response.text :
        typeof data.result === "string" ? data.result :
        typeof data.message === "string" ? data.message :
        null;

      const finished = [
        "completed",
        "done",
        "success",
        "failed",
        "error"
      ].includes(status);

      if (responseText !== null || finished) {
        stopPolling(messageId);

        const failed = ["failed", "error"].includes(status);

        const answer = responseText ||
          (failed
            ? "The PC agent reported that the command failed."
            : "The PC agent marked the command as completed.");

        updateMessage(messageId, {
          status: failed ? "error" : "completed"
        });

        addMessage("assistant", answer);

        updateConnection(
          failed ? "Command failed" : "PC response received",
          failed ? "error" : "connected"
        );

        if (state.callActive && state.callConnected) {
          let spokenReply = answer;

          updateCallTranscript("MH2: " + answer);
          setCallSubtitle(failed ? "Command failed" : "PC response received");

          if (
            data.requiresConfirmation === true ||
            data.awaitingConfirmation === true
          ) {
            state.waitingForConfirmation = true;

            const question =
              "Should I continue? Please say confirm delete or cancel action.";

            addMessage("assistant", question);
            spokenReply += ". " + question;

            updateCallTranscript("MH2: " + answer + "\n\n" + question);
            setCallSubtitle("Waiting for your confirmation");
          }

          state.awaitingPcResponse = true;
          await speak(spokenReply);

          if (state.callActive && state.callConnected && !state.muted) {
            state.awaitingPcResponse = false;
            resumeCallListening(800);
          }
        } else if (
          state.waitingForConfirmation &&
          ["failed", "error"].includes(status)
        ) {
          state.awaitingPcResponse = false;
        }
      }
    } catch (error) {
      console.warn("Polling error:", error);

      if (attempts === 1) {
        updateConnection("Cannot read command status", "error");
      }
    } finally {
      busy = false;
    }
  }, 1500);

  state.pollers.set(messageId, timer);
}

function stopPolling(id) {
  const timer = state.pollers.get(id);
  if (timer) clearInterval(timer);
  state.pollers.delete(id);
}

function stopAllPolling() {
  for (const timer of state.pollers.values()) {
    clearInterval(timer);
  }

  state.pollers.clear();
}

async function toggleRecording() {
  if (!state.callActive || !state.callConnected) {
    toast("Connect the call before recording.");
    return;
  }

  if (state.mediaRecorder && state.mediaRecorder.state === "recording") {
    await stopRecording(true);
    return;
  }

  if (
    !navigator.mediaDevices?.getUserMedia ||
    typeof MediaRecorder === "undefined"
  ) {
    toast("Audio recording is not supported in this browser.");
    return;
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: true
    });

    if (!state.callActive || !state.callConnected) {
      stream.getTracks().forEach(track => track.stop());
      return;
    }

    state.recordingStream = stream;
    state.recordingChunks = [];

    const mime = [
      "audio/webm;codecs=opus",
      "audio/webm",
      "audio/mp4"
    ].find(type => MediaRecorder.isTypeSupported(type));

    state.mediaRecorder = new MediaRecorder(
      stream,
      mime ? { mimeType: mime } : undefined
    );

    const recorder = state.mediaRecorder;

    recorder.ondataavailable = event => {
      if (event.data?.size) {
        state.recordingChunks.push(event.data);
      }
    };

    recorder.onstop = () => {
      state.recordedBlob = new Blob(state.recordingChunks, {
        type: recorder.mimeType || "audio/webm"
      });

      stream.getTracks().forEach(track => track.stop());

      if (state.recordingStream === stream) {
        state.recordingStream = null;
      }

      $("recordingIndicator")?.classList.remove("active");
      $("callRecordBtn")?.classList.remove("active");
      $("callRecordBtn")?.setAttribute("aria-pressed", "false");

      if ($("recordLabel")) $("recordLabel").textContent = "Record";

      if (state.recordedBlob.size && state.callActive) {
        if (confirm("Download the microphone recording?")) {
          downloadRecording();
        }
      }
    };

    recorder.start(250);

    $("recordingIndicator")?.classList.add("active");
    $("callRecordBtn")?.classList.add("active");
    $("callRecordBtn")?.setAttribute("aria-pressed", "true");

    if ($("recordLabel")) $("recordLabel").textContent = "Stop";

    if ($("callNote")) {
      $("callNote").textContent =
        "Recording microphone audio. Obtain consent before recording other people.";
    }

    toast("Microphone recording started.");
  } catch (error) {
    toast("Could not start recording: " + error.message);
  }
}

async function stopRecording(askToDownload = true) {
  const recorder = state.mediaRecorder;

  if (recorder && recorder.state !== "inactive") {
    recorder.stop();
  } else if (state.recordingStream) {
    state.recordingStream.getTracks().forEach(track => track.stop());
    state.recordingStream = null;
  }

  $("recordingIndicator")?.classList.remove("active");
  $("callRecordBtn")?.classList.remove("active");
  $("callRecordBtn")?.setAttribute("aria-pressed", "false");

  if ($("recordLabel")) $("recordLabel").textContent = "Record";
}

function downloadRecording() {
  if (!state.recordedBlob?.size) {
    toast("No recording is available.");
    return;
  }

  const url = URL.createObjectURL(state.recordedBlob);
  const link = document.createElement("a");

  link.href = url;
  link.download = "mh2-call-recording." +
    (state.recordedBlob.type.includes("mp4") ? "mp4" : "webm");

  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
}

function openSettings() {
  if ($("databaseUrl")) {
    $("databaseUrl").value = state.databaseUrl;
  }

  if ($("authToken")) {
    $("authToken").value = state.authToken;
  }

  $("settingsModal")?.classList.add("open");
}

function closeSettings() {
  $("settingsModal")?.classList.remove("open");
}

function resizeInput() {
  const input = $("messageInput");
  if (!input) return;

  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 130) + "px";
}

/* Settings and UI event handlers */

$("settingsBtn")?.addEventListener("click", openSettings);
$("connectionSettings")?.addEventListener("click", openSettings);
$("closeSettings")?.addEventListener("click", closeSettings);

$("settingsModal")?.addEventListener("click", event => {
  if (event.target === $("settingsModal")) closeSettings();
});

document.addEventListener("keydown", event => {
  if (event.key === "Escape") {
    closeSettings();
    if (state.callActive) endCall();
  }
});

$("settingsForm")?.addEventListener("submit", event => {
  event.preventDefault();

  const url = $("databaseUrl").value.trim().replace(/\/+$/, "");
  const token = $("authToken").value.trim();

  if (!/^https:\/\/[a-zA-Z0-9.-]+(?::\d+)?$/.test(url)) {
    toast("Enter a valid HTTPS Firebase Database URL.");
    return;
  }

  try {
    localStorage.setItem(STORAGE.url, url);
    localStorage.setItem(STORAGE.token, token);
  } catch {
    toast("Could not save settings in this browser.");
    return;
  }

  state.databaseUrl = url;
  state.authToken = token;

  closeSettings();
  updateConnection("Firebase configured", "connected");
  toast("Firebase settings saved.");
});

$("testConnection")?.addEventListener("click", async () => {
  const url = $("databaseUrl").value.trim().replace(/\/+$/, "");
  const token = $("authToken").value.trim();

  if (!/^https:\/\/[a-zA-Z0-9.-]+(?::\d+)?$/.test(url)) {
    toast("Enter a valid HTTPS Firebase Database URL.");
    return;
  }

  const oldUrl = state.databaseUrl;
  const oldToken = state.authToken;

  state.databaseUrl = url;
  state.authToken = token;
  updateConnection("Testing Firebase...");

  try {
    await databaseRequest("commands", { method: "GET" });

    localStorage.setItem(STORAGE.url, url);
    localStorage.setItem(STORAGE.token, token);

    updateConnection("Firebase connection successful", "connected");
    toast("Firebase connection successful.");
  } catch (error) {
    state.databaseUrl = oldUrl;
    state.authToken = oldToken;

    updateConnection("Connection test failed", "error");
    toast("Connection failed: " + error.message);
  }
});

$("composer")?.addEventListener("submit", event => {
  event.preventDefault();
  sendCommand(undefined, "text");
});

$("messageInput")?.addEventListener("input", resizeInput);

$("messageInput")?.addEventListener("keydown", event => {
  if (
    event.key === "Enter" &&
    !event.shiftKey &&
    !event.isComposing
  ) {
    event.preventDefault();
    sendCommand(undefined, "text");
  }
});

document.querySelectorAll("[data-command]").forEach(button => {
  button.addEventListener("click", () => {
    sendCommand(button.dataset.command, "text");
  });
});

$("startCallBtn")?.addEventListener("click", startCall);
$("endCallBtn")?.addEventListener("click", endCall);

$("callListenBtn")?.addEventListener("click", () => {
  startListening(false);
});

$("micBtn")?.addEventListener("click", () => {
  if (!state.voiceSupported) {
    toast("Voice recognition is unavailable. Try Chrome or Edge.");
    return;
  }

  if (state.callActive) {
    startListening(false);
    return;
  }

  if (state.recognitionBusy) {
    try { state.recognition?.stop(); } catch {}
    return;
  }

  try {
    state.recognition.start();
  } catch {
    toast("Microphone is busy. Try again.");
  }
});



$("callMuteBtn")?.addEventListener("click", () => {
  if (!state.callActive || !state.callConnected) {
    toast("Connect the call first.");
    return;
  }

  state.muted = !state.muted;

  $("callMuteBtn")?.classList.toggle("active", state.muted);
  $("callMuteBtn")?.setAttribute(
    "aria-pressed",
    String(state.muted)
  );

  if ($("muteLabel")) {
    $("muteLabel").textContent = state.muted ? "Unmute" : "Mute";
  }

  if (state.muted) {
    cancelListenRestart();
    stopSpeech();

    try {
      state.recognition?.abort();
    } catch {}

    setCallSubtitle("Microphone muted");
  } else {
    setCallSubtitle("Preparing microphone...");
    resumeCallListening(400);
  }
});


$("callSpeakerBtn")?.addEventListener("click", async () => {
  if (!state.callActive) return;

  state.speakerMode = !state.speakerMode;

  $("callSpeakerBtn")?.classList.toggle("active", state.speakerMode);
  $("callSpeakerBtn")?.setAttribute(
    "aria-pressed",
    String(state.speakerMode)
  );

  if ($("speakerLabel")) {
    $("speakerLabel").textContent =
      state.speakerMode ? "Speaker On" : "Speaker";
  }

  if (state.speakerMode && state.audioContext) {
    try { await state.audioContext.resume(); } catch {}
  }

  toast(
    state.speakerMode
      ? "Speaker preference enabled."
      : "Speaker preference disabled."
  );
});

$("callDialBtn")?.addEventListener("click", () => {
  const dialpad = $("dialpad");
  if (!dialpad) return;

  const open = !dialpad.classList.contains("open");

  dialpad.classList.toggle("open", open);
  $("callDialBtn")?.classList.toggle("active", open);
  $("callDialBtn")?.setAttribute("aria-pressed", String(open));
});

document.querySelectorAll("[data-digit]").forEach(button => {
  button.addEventListener("click", () => {
    if (!state.callActive || !state.callConnected) return;

    const digit = button.dataset.digit;
    const current = $("callTranscript")?.textContent || "";

    updateCallTranscript(current + "\nKeypad: " + digit);
    toast("Keypad display only. DTMF is not implemented.");
  });
});

$("callRecordBtn")?.addEventListener("click", toggleRecording);

$("newChatBtn")?.addEventListener("click", () => {
  if (!confirm("Start a new chat and clear the current chat history?")) return;

  stopAllPolling();
  state.messages = [];
  saveHistory();
  renderAll();

  toast("New chat started.");
});

$("clearChat")?.addEventListener("click", () => {
  stopAllPolling();
  state.messages = [];
  saveHistory();
  renderAll();

  toast("Chat history cleared.");
});

$("exportChat")?.addEventListener("click", () => {
  const content = state.messages.map(message =>
    "[" + new Date(message.timestamp).toLocaleString() + "] " +
    (message.role === "user" ? "You" : "MH2 Assistant") +
    ": " + message.text
  ).join("\n\n");

  const blob = new Blob([content], {
    type: "text/plain;charset=utf-8"
  });

  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");

  link.href = url;
  link.download = "mh2-pc-assistant-chat.txt";
  link.click();

  setTimeout(() => URL.revokeObjectURL(url), 1000);
});

setupRecognition();
renderAll();

updateConnection(
  state.databaseUrl ? "Firebase configured" : "Firebase not configured",
  state.databaseUrl ? "connected" : ""
);

if (!window.isSecureContext && location.hostname !== "localhost") {
  console.warn(
    "Microphone access normally requires HTTPS or localhost."
  );
}
