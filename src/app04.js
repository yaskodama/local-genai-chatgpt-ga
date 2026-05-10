document.addEventListener("DOMContentLoaded", () => {
  const SID_KEY = "abcl_sid";
  let sid = localStorage.getItem(SID_KEY);
  if (!sid) {
    sid = "s-" + Math.random().toString(16).slice(2) + "-" + Date.now();
    localStorage.setItem(SID_KEY, sid);
  }
  let afterEvt = -1;
  let afterLog = -1;
  const out = document.getElementById("out");
  const logBox = document.getElementById("log");
  const eventsBox = document.getElementById("events");
  const repliesBox = document.getElementById("replies");
  const treeBox = document.getElementById("tree");
  const msgNodes = new Map();

  function text(id) {
    return document.getElementById(id);
  }

  function extractId(line) {
    const m = line.match(/id=([^\s]+)/);
    return m ? m[1] : null;
  }

  function ensureNode(id, title) {
    if (msgNodes.has(id)) return msgNodes.get(id);
    if (!treeBox) return null;
    const root = document.createElement("div");
    root.style.border = "1px solid #333";
    root.style.borderRadius = "8px";
    root.style.padding = "6px";
    root.style.margin = "6px 0";
    const head = document.createElement("div");
    head.textContent = title;
    head.style.color = "#55ff55";
    head.style.fontWeight = "700";
    const body = document.createElement("div");
    body.style.marginTop = "4px";
    body.style.paddingLeft = "10px";
    root.appendChild(head);
    root.appendChild(body);
    treeBox.appendChild(root);
    const node = { root, head, body };
    msgNodes.set(id, node);
    return node;
  }

  function addTreeChild(id, text, kind) {
    const node = ensureNode(id, "id=" + id);
    if (!node) return;
    const row = document.createElement("div");
    row.textContent = text;
    row.style.whiteSpace = "pre-wrap";
    if (kind === "reply") row.style.color = "#66ccff";
    else if (kind === "failed") {
      row.style.color = "#ff5555";
      row.style.fontWeight = "700";
    } else row.style.color = "#ffff66";
    node.body.appendChild(row);
  }

  function parseAtom(s) {
    s = s.trim();
    if (!s) return null;
    if (
      (s.startsWith("\"") && s.endsWith("\"")) ||
      (s.startsWith("'") && s.endsWith("'"))
    ) {
      return s.substring(1, s.length - 1);
    }
    if (s === "true") return true;
    if (s === "false") return false;
    if (s === "null") return null;
    const n = Number(s);
    if (Number.isFinite(n)) return n;
    return s;
  }

  function appendEventLine(line) {
    if (!eventsBox) return;

    const row = document.createElement("div");
    row.textContent = line;
    row.style.whiteSpace = "pre-wrap";

    if (line.startsWith("[FAILED]")) {
      row.style.color = "#ff5555";
      row.style.fontWeight = "700";
    } else if (line.startsWith("[ACCEPTED]")) {
      row.style.color = "#55ff55";
    } else if (line.startsWith("[REPLY]")) {
      row.style.color = "#66ccff";
    } else {
      row.style.color = "#ffff66";
    }

    eventsBox.appendChild(row);
    eventsBox.scrollTop = eventsBox.scrollHeight;

    const id = extractId(line);
    if (!id) return;

    if (line.startsWith("[ACCEPTED]")) {
      const node = ensureNode(id, line);
      if (node) {
        node.head.textContent = line;
        node.head.style.color = "#55ff55";
      }
    } else if (line.startsWith("[FAILED]")) {
      addTreeChild(id, line, "failed");
    } else if (line.startsWith("[REPLY]")) {
      addTreeChild(id, line, "reply");
    } else {
      addTreeChild(id, line, "event");
    }
  }

  async function pollLogs() {
    try {
      const r = await fetch("/api/log?sid=" + encodeURIComponent(sid) + "&after=" + afterLog);
      if (r.ok) {
        const j = await r.json();
        if (typeof j.next === "number") afterLog = j.next;
        if (j.lines && j.lines.length && logBox) {
          logBox.textContent += j.lines.join("\n") + "\n";
          logBox.scrollTop = logBox.scrollHeight;
        }
      }
    } catch (e) {
      if (out) out.textContent = "poll log error: " + e;
    }
    setTimeout(pollLogs, 700);
  }

  async function pollEvents() {
    try {
      const r = await fetch("/api/events?after=" + afterEvt);
      if (r.ok) {
        const j = await r.json();
        if (typeof j.next === "number") afterEvt = j.next;
        if (j.lines && j.lines.length) {
          for (const line of j.lines) {
            appendEventLine(line);
            if (line.startsWith("[REPLY]") && repliesBox) {
              repliesBox.textContent += line + "\n";
              repliesBox.scrollTop = repliesBox.scrollHeight;
            }
          }
        }
      }
    } catch (e) {
      if (out) out.textContent = "poll events error: " + e;
    }
    setTimeout(pollEvents, 700);
  }

  async function sendJsonMessage() {
    const to = text("to")?.value || "";
    const method = text("method")?.value || "";
    const argsRaw = text("args")?.value || "";
    const unsafe = text("unsafe")?.checked || false;
    const payload = {
      sid,
      to,
      method,
      args: argsRaw
        .split(",")
        .map(s => s.trim())
        .filter(s => s.length > 0)
        .map(parseAtom),
      from: "browser",
      unsafe
    };

    try {
      if (out) out.textContent = "sending...";
      const r = await fetch("/api/json/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const t = await r.text();
      if (out) out.textContent = "send: " + t;
    } catch (e) {
      if (out) out.textContent = "send error: " + e;
    }
  }

  function openBrowserConsolePage() {
  const w = window.open("", "_blank", "width=1000,height=700");
  if (!w) return;

  const html = `
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>AIPL Browser Console</title>
  <style>
    body { font-family: monospace; margin: 0; background: #111; color: #ddd; }
    #consoleOut {
      height: calc(100vh - 60px);
      overflow: auto;
      padding: 12px;
      white-space: pre-wrap;
      background: #000;
      color: #0f0;
    }
    #inputRow {
      display: flex;
      gap: 8px;
      padding: 10px;
      background: #181818;
      border-top: 1px solid #333;
    }
    #cmd {
      flex: 1;
      padding: 8px;
      background: #222;
      color: #fff;
      border: 1px solid #555;
    }
    button {
      padding: 8px 12px;
      background: #333;
      color: #fff;
      border: 1px solid #666;
      cursor: pointer;
    }
    button:hover { background: #444; }
  </style>
</head>
<body>
  <div id="consoleOut"></div>
  <div id="inputRow">
    <input id="cmd" type="text" placeholder="Browser ABCL command">
    <button id="runBtn">Run</button>
  </div>
</body>
</html>`;
      
  w.document.open();
  w.document.write(html);
  w.document.close();

  const consoleOut = w.document.getElementById("consoleOut");
  const cmdInput = w.document.getElementById("cmd");
  const runBtn = w.document.getElementById("runBtn");

  // ★ここが「ブラウザだけで動く簡易REPL」
  function runLocal(cmd) {
    consoleOut.textContent += ">>> " + cmd + "\n";

    try {
      // とりあえず簡易評価（後でABCL interpreterに置き換え）
      let result = eval(cmd);
      if (result !== undefined) {
        consoleOut.textContent += result + "\n";
      }
    } catch (e) {
      consoleOut.textContent += "[ERROR] " + e + "\n";
    }

    consoleOut.scrollTop = consoleOut.scrollHeight;
  }
      
  runBtn.onclick = () => {
    const cmd = cmdInput.value.trim();
    if (!cmd) return;
    runLocal(cmd);
    cmdInput.value = "";
  };

  cmdInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") runBtn.onclick();
  });

    consoleOut.textContent =
    "AIPL Browser Console (Local)\n" +
    "This runs JavaScript locally (next step: ABCL interpreter)\n\n";
  }

  async function runReplCommand(cmd, consoleOutput) {
    try {
      const r = await fetch("/api/repl", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sid, command: cmd })
      });
      const t = await r.text();
      if (t && t.trim() !== "") {
        consoleOutput.textContent += t;
        if (!t.endsWith("\n")) consoleOutput.textContent += "\n";
        consoleOutput.scrollTop = consoleOutput.scrollHeight;
      }
    } catch (e) {
      consoleOutput.textContent += "[ERROR] /api/repl is not available: " + e + "\n";
      consoleOutput.scrollTop = consoleOutput.scrollHeight;
    }
  }

  function startConsoleStreaming(consoleOutput) {
    let consoleAfterLog = -1;
    let consoleAfterEvt = -1;

    async function poll() {
      try {
        const r1 = await fetch(
          "/api/log?sid=" + encodeURIComponent(sid) + "&after=" + consoleAfterLog
        );
        if (r1.ok) {
          const j1 = await r1.json();
          if (typeof j1.next === "number") consoleAfterLog = j1.next;
          if (j1.lines && j1.lines.length) {
            j1.lines.forEach(line => {
              consoleOutput.textContent += line + "\n";
            });
          }
        }

        const r2 = await fetch("/api/events?after=" + consoleAfterEvt);
        if (r2.ok) {
          const j2 = await r2.json();
          if (typeof j2.next === "number") consoleAfterEvt = j2.next;
          if (j2.lines && j2.lines.length) {
            j2.lines.forEach(line => {
              consoleOutput.textContent += line + "\n";
            });
          }
        }

      consoleOutput.scrollTop = consoleOutput.scrollHeight;
      } catch (e) {
        consoleOutput.textContent += "[poll error] " + e + "\n";
        consoleOutput.scrollTop = consoleOutput.scrollHeight;
      }

      setTimeout(poll, 200);
    }

    poll();
  }
	  
  function openConsolePage() {
    const w = window.open("", "_blank", "width=1000,height=700");
    if (!w) {
      if (out) out.textContent = "Popup blocked";
      return;
    }

    const html = `
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>AIPL Console</title>
  <style>
    body { font-family: monospace; margin: 0; background: #111; color: #ddd; }
    #bar { padding: 10px; background: #222; border-bottom: 1px solid #333; }
    #consoleOut {
      height: calc(100vh - 120px);
      overflow: auto;
      padding: 12px;
      white-space: pre-wrap;
      background: #000;
      color: #0f0;
    }
   #inputRow {
      display: flex;
      gap: 8px;
      padding: 10px;
      background: #181818;
      border-top: 1px solid #333;
    }
   #cmd {
      flex: 1;
      padding: 8px;
      background: #222;
      color: #fff;
      border: 1px solid #555;
    }
    button {
      padding: 8px 12px;
      background: #333;
      color: #fff;
      border: 1px solid #666;
      cursor: pointer;
    }
    button:hover { background: #444; }
    .quick { margin-right: 8px; }
  </style>
</head>
<body>
  <div id="bar">
    <button class="quick" id="btnLoad">load sample</button>
    <button class="quick" id="btnCompile">compile</button>
    <button class="quick" id="btnMain">send calc.main();</button>
    <button class="quick" id="btnAdd">send calc.add(3,4);</button>
    <button class="quick" id="btnNewActor">var c = new Calc();</button>
  </div>
  <div id="consoleOut"></div>
  <div id="inputRow">
    <input id="cmd" type="text" placeholder="Enter AIPL command">
    <button id="runBtn">Run</button>
  </div>
</body>
</html>`;

    w.document.open();
    w.document.write(html);
    w.document.close();

    const consoleOut = w.document.getElementById("consoleOut");
    const cmdInput = w.document.getElementById("cmd");
    const runBtn = w.document.getElementById("runBtn");

    startConsoleStreaming(consoleOut);

    const run = () => {
      const cmd = cmdInput.value.trim();
      if (!cmd) return;
      consoleOut.textContent += ">>> " + cmd + "\n";
      consoleOut.scrollTop = consoleOut.scrollHeight;
      runReplCommand(cmd, consoleOut);
      cmdInput.value = "";
    };

    runBtn.addEventListener("click", run);
    cmdInput.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") run();
    });

    w.document.getElementById("btnLoad").addEventListener("click", () => {
      consoleOut.textContent += ">>> load web_calc1.abcl\n";
      consoleOut.scrollTop = consoleOut.scrollHeight;
      runReplCommand("load web_calc1.abcl", consoleOut);
    });

    w.document.getElementById("btnCompile").addEventListener("click", () => {
      consoleOut.textContent += ">>> compile\n";
      consoleOut.scrollTop = consoleOut.scrollHeight;
      runReplCommand("compile", consoleOut);
    });

    w.document.getElementById("btnMain").addEventListener("click", () => {
      consoleOut.textContent += ">>> send calc.main();\n";
      consoleOut.scrollTop = consoleOut.scrollHeight;
      runReplCommand("send calc.main();", consoleOut);
    });

    w.document.getElementById("btnAdd").addEventListener("click", () => {
      consoleOut.textContent += ">>> send calc.add(3,4);\n";
      consoleOut.scrollTop = consoleOut.scrollHeight;
      runReplCommand("send calc.add(3,4);", consoleOut);
    });

    w.document.getElementById("btnNewActor").addEventListener("click", () => {
      consoleOut.textContent += ">>> var c = new Calc();\n";
      consoleOut.scrollTop = consoleOut.scrollHeight;
      runReplCommand("var c = new Calc();", consoleOut);
    });
    consoleOut.textContent =
      "AIPL Web Console\n" +
      "sid=" + sid + "\n" +
      "Open from http://localhost:8080/\n\n";
  }

  function installButtons() {
    const host = document.body;
    const wrap = document.createElement("div");
    wrap.style.marginTop = "12px";
    wrap.style.padding = "8px";
    wrap.style.border = "1px solid #ccc";
    wrap.style.background = "#fafafa";

    const title = document.createElement("div");
    title.textContent = "Console / Quick Operations";
    title.style.fontWeight = "700";
    title.style.marginBottom = "8px";
    wrap.appendChild(title);

    const openBtn = document.createElement("button");
    openBtn.textContent = "Open Console";
    openBtn.style.marginRight = "8px";
    openBtn.onclick = openConsolePage;
    wrap.appendChild(openBtn);

    const browserBtn = document.createElement("button");
    browserBtn.textContent = "Open Browser Console";
    browserBtn.style.marginRight = "8px";
    browserBtn.onclick = openBrowserConsolePage;
    wrap.appendChild(browserBtn);

    const sendBtn = document.createElement("button");
    sendBtn.textContent = "Send Message";
    sendBtn.style.marginRight = "8px";
    sendBtn.onclick = sendJsonMessage;
    wrap.appendChild(sendBtn);

    const refreshBtn = document.createElement("button");
    refreshBtn.textContent = "Refresh Events";
    refreshBtn.onclick = pollEvents;
    wrap.appendChild(refreshBtn);


    host.insertBefore(wrap, host.firstChild);
  }

  window.send = sendJsonMessage;
  window.openConsolePage = openConsolePage;

  installButtons();

  if (out) out.textContent = "JS loaded, sid=" + sid;

  pollLogs();
  pollEvents();
});
