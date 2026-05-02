// ABCL/c+ IDE frontend
// Talks to the running OCaml process via the existing web_gateway endpoints:
//   POST /api/repl      — send a REPL command, get textual output back
//   GET  /api/log       — stream of log lines (polled)
//   WS   /ws?sid=<sid>  — push channel for logs/events/replies
//
// Layout: command input / output / current actors / source code display.

(() => {
  const SID_KEY = "abcl_ide_sid";
  let sid = localStorage.getItem(SID_KEY);
  if (!sid) {
    sid = "ide-" + Math.random().toString(16).slice(2) + "-" + Date.now();
    localStorage.setItem(SID_KEY, sid);
  }

  const els = {
    cmdInput:       document.getElementById("cmd-input"),
    btnSend:        document.getElementById("btn-send"),
    btnLoadFile:    document.getElementById("btn-load-file"),
    btnCompile:     document.getElementById("btn-compile"),
    btnList:        document.getElementById("btn-list"),
    btnClear:       document.getElementById("btn-clear"),
    btnActorsRefresh: document.getElementById("btn-actors-refresh"),
    btnAutoRefresh: document.getElementById("btn-auto-refresh"),
    btnSrcAst:      document.getElementById("btn-src-ast"),
    btnSrcRefresh:  document.getElementById("btn-src-refresh"),
    outBody:        document.getElementById("out-body"),
    outStatus:      document.getElementById("out-status"),
    actorsBody:     document.getElementById("actors-body"),
    actorsCount:    document.getElementById("actors-count"),
    srcBody:        document.getElementById("src-body"),
    srcTarget:      document.getElementById("src-target"),
    connStatus:     document.getElementById("conn-status"),
    // File menu / directory browser
    menuFile:       document.getElementById("menu-file"),
    menuFileBtn:    document.getElementById("menu-file-btn"),
    browserUp:      document.getElementById("browser-up"),
    browserPath:    document.getElementById("browser-path"),
    browserGo:      document.getElementById("browser-go"),
    browserExt:     document.getElementById("browser-ext"),
    browserBody:    document.getElementById("browser-body"),
  };

  // --- output pane ---------------------------------------------------------
  function appendOut(text, cls) {
    const span = document.createElement("span");
    if (cls) span.className = cls;
    span.textContent = text;
    els.outBody.appendChild(span);
    els.outBody.scrollTop = els.outBody.scrollHeight;
  }
  function appendLine(text, cls) { appendOut(text + "\n", cls); }

  els.btnClear.addEventListener("click", () => { els.outBody.innerHTML = ""; });

  // --- command input / history --------------------------------------------
  const HIST_KEY = "abcl_ide_hist";
  let history = [];
  try { history = JSON.parse(localStorage.getItem(HIST_KEY) || "[]"); } catch {}
  let histIdx = history.length;

  function pushHistory(cmd) {
    cmd = cmd.trim();
    if (!cmd) return;
    if (history[history.length - 1] !== cmd) {
      history.push(cmd);
      if (history.length > 200) history.shift();
      localStorage.setItem(HIST_KEY, JSON.stringify(history));
    }
    histIdx = history.length;
  }

  els.cmdInput.addEventListener("keydown", (e) => {
    // Shift+Enter = send; Enter alone inserts newline for multi-line source.
    if (e.key === "Enter" && e.shiftKey) {
      e.preventDefault();
      sendCurrent();
      return;
    }
    if (e.key === "ArrowUp" && e.ctrlKey) {
      e.preventDefault();
      if (histIdx > 0) {
        histIdx--;
        els.cmdInput.value = history[histIdx] || "";
      }
    } else if (e.key === "ArrowDown" && e.ctrlKey) {
      e.preventDefault();
      if (histIdx < history.length - 1) {
        histIdx++;
        els.cmdInput.value = history[histIdx] || "";
      } else {
        histIdx = history.length;
        els.cmdInput.value = "";
      }
    }
  });

  els.btnSend.addEventListener("click", sendCurrent);

  els.btnLoadFile.addEventListener("click", () => {
    const f = prompt("読み込むファイル名 (例: viz_philosophers.abcl):");
    if (!f) return;
    runRepl("load " + f.trim());
  });

  els.btnCompile.addEventListener("click", () => runRepl("compile"));
  els.btnList.addEventListener("click", () => runRepl("list"));

  function sendCurrent() {
    const txt = els.cmdInput.value;
    if (!txt.trim()) return;
    pushHistory(txt);
    runRepl(txt);
    els.cmdInput.value = "";
  }

  // --- REPL request --------------------------------------------------------
  let busy = false;
  async function runRepl(command, opts = {}) {
    const { silent = false } = opts;
    if (!silent) {
      appendLine("ABCL/c+> " + command.split("\n").join("\n          "), "cmd");
    }
    if (busy && !silent) {
      appendLine("[busy — wait for previous command to finish]", "sys");
      return "";
    }
    busy = true;
    els.outStatus.textContent = "実行中…";
    try {
      const r = await fetch("/api/repl", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command, sid }),
      });
      const text = await r.text();
      if (!silent) {
        if (!r.ok) appendLine(text, "err");
        else if (text && text !== "OK") appendOut(text.endsWith("\n") ? text : text + "\n");
        else appendLine("OK", "ok");
      }
      // opportunistic actors refresh after commands likely to change state
      if (/^\s*(compile|load\s|script\s|send\s|ssend\s|reset|clear)/i.test(command)) {
        setTimeout(refreshActors, 150);
      }
      return text;
    } catch (e) {
      if (!silent) appendLine("[network error] " + e.message, "err");
      return "";
    } finally {
      busy = false;
      els.outStatus.textContent = "";
    }
  }

  // --- actors list ---------------------------------------------------------
  // We piggy-back on the REPL `actors` command and parse its text output.
  // Format of each entry produced by repl_thread.ml:
  //   - <name> : <type>
  //       mbox: <n>
  //       methods: m1, m2, ...

  let selectedActor = null;
  let autoRefresh = true;
  let autoTimer = null;

  function renderActors(list) {
    els.actorsCount.textContent = String(list.length);
    if (list.length === 0) {
      els.actorsBody.innerHTML =
        '<div class="actor-empty">まだアクタが登録されていません。<br>'
        + '<code>compile</code> を実行するとアクタが生成されます。</div>';
      return;
    }
    els.actorsBody.innerHTML = "";
    for (const a of list) {
      const row = document.createElement("div");
      row.className = "actor-row";
      if (a.name === selectedActor) row.classList.add("selected");
      row.innerHTML =
        '<div><span class="actor-name"></span>'
        + '<span class="actor-class"></span></div>'
        + '<div class="actor-meta"></div>';
      row.querySelector(".actor-name").textContent = a.name;
      const cls = a.type || ("actor(" + (a.class || "?") + ")");
      row.querySelector(".actor-class").textContent = ": " + cls;
      const meta = [];
      if (typeof a.mbox === "number") meta.push("mbox=" + a.mbox);
      else if (a.mbox)                meta.push("mbox=" + a.mbox);
      const methodsStr = Array.isArray(a.methods)
        ? a.methods.join(", ")
        : (a.methods || "");
      if (methodsStr) meta.push("methods: " + methodsStr);
      row.querySelector(".actor-meta").textContent = meta.join("    ");
      row.addEventListener("click", () => selectActor(a.name));
      els.actorsBody.appendChild(row);
    }
  }

  // Pull the actor table directly (no REPL round-trip, no stdout spam on
  // the server side).
  async function refreshActors() {
    try {
      const r = await fetch("/api/actors");
      if (!r.ok) return;
      const list = await r.json();
      renderActors(Array.isArray(list) ? list : []);
    } catch (e) {
      // Silent: actor list failures shouldn't spam the output pane.
    }
  }

  els.btnActorsRefresh.addEventListener("click", refreshActors);

  function setAutoRefresh(on) {
    autoRefresh = on;
    els.btnAutoRefresh.textContent = "自動: " + (on ? "ON" : "OFF");
    if (autoTimer) { clearInterval(autoTimer); autoTimer = null; }
    if (on) autoTimer = setInterval(refreshActors, 3000);
  }
  els.btnAutoRefresh.addEventListener("click", () => setAutoRefresh(!autoRefresh));

  // --- source display ------------------------------------------------------
  async function selectActor(name) {
    selectedActor = name;
    // update selection highlight without re-fetching
    [...els.actorsBody.querySelectorAll(".actor-row")].forEach(r => {
      r.classList.toggle(
        "selected",
        r.querySelector(".actor-name")?.textContent === name
      );
    });
    els.srcTarget.textContent = "target: " + name;
    els.srcBody.textContent = "(読み込み中…)";
    const text = await runRepl("pprint " + name, { silent: true });
    els.srcBody.textContent = text && text !== "OK" ? text : "(ソースが取得できませんでした)";
  }

  els.btnSrcRefresh.addEventListener("click", () => {
    if (selectedActor) selectActor(selectedActor);
  });

  els.btnSrcAst.addEventListener("click", async () => {
    if (!selectedActor) {
      els.srcBody.textContent = "アクタ／クラスを先に選択してください。";
      return;
    }
    els.srcTarget.textContent = "AST: " + selectedActor;
    els.srcBody.textContent = "(読み込み中…)";
    const text = await runRepl("ast " + selectedActor, { silent: true });
    els.srcBody.textContent = text && text !== "OK" ? text : "(AST が取得できませんでした)";
  });

  // --- File menu (directory browser) --------------------------------------
  const BROWSER_DIR_KEY = "abcl_ide_browser_dir";
  const BROWSER_EXT_KEY = "abcl_ide_browser_ext";
  let browserCurrent = { dir: ".", abs: "", parent: "" };

  function closeMenu() { els.menuFile.classList.remove("open"); }
  function openMenu()  { els.menuFile.classList.add("open"); }

  // Load saved dir / ext filter
  const savedDir = localStorage.getItem(BROWSER_DIR_KEY);
  const savedExt = localStorage.getItem(BROWSER_EXT_KEY);
  if (savedExt !== null && [...els.browserExt.options].some(o => o.value === savedExt)) {
    els.browserExt.value = savedExt;
  }

  els.menuFileBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    const willOpen = !els.menuFile.classList.contains("open");
    if (willOpen) {
      openMenu();
      browseDir(savedDir || browserCurrent.dir || ".");
    } else {
      closeMenu();
    }
  });

  document.addEventListener("click", (e) => {
    if (!els.menuFile.contains(e.target)) closeMenu();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeMenu();
  });

  // Pick the REPL command to run for a given file.
  function commandForFile(path) {
    const lower = path.toLowerCase();
    if (lower.endsWith(".bat"))  return "script " + path;
    if (lower.endsWith(".abcl")) return "load " + path;
    return null;  // unknown extension: don't do anything automatic
  }

  function joinPath(dir, name) {
    if (!dir || dir === ".") return name;
    if (dir === "/")          return "/" + name;
    if (dir.endsWith("/"))    return dir + name;
    return dir + "/" + name;
  }

  function renderBrowser(data) {
    const body = els.browserBody;
    body.innerHTML = "";

    if (data.error) {
      const e = document.createElement("div");
      e.className = "browser-error";
      e.textContent = "[error] " + data.error;
      body.appendChild(e);
      return;
    }

    // Show parent (.. entry) when we're not at the root
    if (data.parent && data.parent !== data.abs) {
      const up = document.createElement("div");
      up.className = "browser-item parent";
      up.innerHTML = '<span class="icon">↰</span><span class="name">..</span>';
      up.addEventListener("click", () => browseDir(data.parent));
      body.appendChild(up);
    }

    for (const d of (data.dirs || [])) {
      const row = document.createElement("div");
      row.className = "browser-item dir";
      row.innerHTML = '<span class="icon">📁</span><span class="name"></span>';
      row.querySelector(".name").textContent = d + "/";
      row.addEventListener("click", () => browseDir(joinPath(data.dir, d)));
      body.appendChild(row);
    }

    for (const f of (data.files || [])) {
      const row = document.createElement("div");
      row.className = "browser-item file";
      // Prefer the absolute path so the REPL can open the file regardless of
      // its current working directory (falls back to the browse-relative
      // path if the server didn't return one).
      const fullPath =
        data.abs ? joinPath(data.abs, f) : joinPath(data.dir, f);
      const cmd = commandForFile(fullPath);
      const action = cmd ? cmd.split(" ")[0] : "(no-op)";
      row.innerHTML =
        '<span class="icon">📄</span>'
        + '<span class="name"></span>'
        + '<span class="path" style="margin-left:auto; color:var(--fg-muted); font-size:11px;"></span>';
      row.querySelector(".name").textContent = f;
      row.querySelector(".path").textContent = action;
      row.title = cmd ? (cmd) : "(no runner for this extension)";
      row.addEventListener("click", () => {
        if (!cmd) return;
        closeMenu();
        appendLine("[file] " + cmd, "sys");
        runRepl(cmd);
      });
      body.appendChild(row);
    }

    if ((!data.dirs || data.dirs.length === 0)
        && (!data.files || data.files.length === 0)) {
      const em = document.createElement("div");
      em.className = "browser-empty";
      em.textContent = "(該当するフォルダ／ファイルがありません)";
      body.appendChild(em);
    }
  }

  async function browseDir(dir) {
    const ext = els.browserExt.value || "";
    els.browserPath.value = dir;
    els.browserBody.innerHTML =
      '<div class="browser-empty">読み込み中…</div>';
    const url = "/api/browse?dir=" + encodeURIComponent(dir)
              + "&ext=" + encodeURIComponent(ext);
    try {
      const r = await fetch(url);
      const data = await r.json();
      if (data && !data.error) {
        browserCurrent = {
          dir: data.dir,
          abs: data.abs || data.dir,
          parent: data.parent || ""
        };
        localStorage.setItem(BROWSER_DIR_KEY, data.dir);
      }
      localStorage.setItem(BROWSER_EXT_KEY, ext);
      renderBrowser(data || {});
    } catch (e) {
      renderBrowser({ error: "network: " + e.message });
    }
  }

  els.browserUp.addEventListener("click", (e) => {
    e.stopPropagation();
    if (browserCurrent.parent) {
      browseDir(browserCurrent.parent);
    } else {
      browseDir(joinPath(browserCurrent.dir || ".", ".."));
    }
  });
  els.browserGo.addEventListener("click", (e) => {
    e.stopPropagation();
    const p = els.browserPath.value.trim();
    if (p) browseDir(p);
  });
  els.browserPath.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      e.stopPropagation();
      const p = els.browserPath.value.trim();
      if (p) browseDir(p);
    }
  });
  els.browserExt.addEventListener("change", () => {
    browseDir(browserCurrent.dir || ".");
  });

  // --- WebSocket (log / event push) ---------------------------------------
  function connectWs() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const url = proto + "//" + location.host + "/ws?sid=" + encodeURIComponent(sid);
    let ws;
    try { ws = new WebSocket(url); }
    catch (e) { els.connStatus.textContent = "WS unavailable"; return; }
    ws.addEventListener("open",  () => { els.connStatus.textContent = "● 接続済 (sid=" + sid + ")"; });
    ws.addEventListener("close", () => {
      els.connStatus.textContent = "○ 切断 — 再接続します";
      setTimeout(connectWs, 1500);
    });
    ws.addEventListener("error", () => { els.connStatus.textContent = "× エラー"; });
    ws.addEventListener("message", (e) => {
      let msg;
      try { msg = JSON.parse(e.data); } catch { return; }
      if (!msg || !msg.type) return;
      switch (msg.type) {
        case "log":
          appendLine(msg.line || "");
          break;
        case "event":
          appendLine(msg.line || "", "sys");
          break;
        case "reply":
          appendLine(msg.line || "", "ok");
          break;
      }
    });
  }

  // --- init ----------------------------------------------------------------
  connectWs();
  setAutoRefresh(true);
  refreshActors();
  appendLine("ABCL/c+ IDE 起動。Shift+Enter でコマンド送信、Ctrl+↑/↓ で履歴。", "sys");
  els.cmdInput.focus();
})();
