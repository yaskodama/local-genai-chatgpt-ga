document.body.innerHTML = `
<div id="bar" style="padding:10px;background:#222;border-bottom:1px solid #333;">
  <button class="quick" id="btnLoad">load philosophers</button>
  <button class="quick" id="btnCompile">compile</button>
  <button class="quick" id="btnStart">send table.start();</button>
  <button class="quick" id="btnP0">send p0.start();</button>
  <button class="quick" id="btnP1">send p1.start();</button>
  <button class="quick" id="btnP2">send p2.start();</button>
  <button class="quick" id="btnP3">send p3.start();</button>
  <button class="quick" id="btnP4">send p4.start();</button>
  <button class="quick" id="btnViz" style="margin-left:12px;background:#264;color:#cfc;">Open Visualization</button>
  <button class="quick" id="btnClear">clear</button>
</div>

<div id="consoleOut"
     style="height:calc(100vh - 120px);overflow:auto;padding:12px;white-space:pre-wrap;background:#000;color:#0f0;font-family:monospace;"></div>
<div id="inputRow"
     style="display:flex;gap:8px;padding:10px;background:#181818;border-top:1px solid #333;">
  <input id="cmd" type="text" placeholder="Enter AIPL command"
         style="flex:1;padding:8px;background:#222;color:#fff;border:1px solid #555;">
  <button id="runBtn"
          style="padding:8px 12px;background:#333;color:#fff;border:1px solid #666;cursor:pointer;">Run</button>
</div>
`;

const SID_KEY = "abcl_sid";
let sid = localStorage.getItem(SID_KEY);
if (!sid) {
  sid = "s-" + Math.random().toString(16).slice(2) + "-" + Date.now();
  localStorage.setItem(SID_KEY, sid);
}

const consoleOut = document.getElementById("consoleOut");
const cmdInput = document.getElementById("cmd");
const runBtn = document.getElementById("runBtn");


let consoleAfterLog = -1;
let consoleAfterEvt = -1;
let history = [];
let historyIndex = -1;

function appendConsole(line) {
  if (!line) return;
  consoleOut.textContent += line;
  if (!line.endsWith("\n")) consoleOut.textContent += "\n";
  consoleOut.scrollTop = consoleOut.scrollHeight;
}

async function runReplCommand(cmd) {
  try {
    const r = await fetch("/api/repl", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sid, command: cmd })
    });

    const t = await r.text();
    if (t && t.trim() !== "") {
      appendConsole(t);
    }
  } catch (e) {
    appendConsole("[ERROR] /api/repl is not available: " + e);
  }
}

function startConsoleStreaming() {
  async function poll() {
    try {
      // Server Console は global web_logs を見る（sid を付けない）。
      // これで print() の出力がブラウザ側にも流れてくる。
      const r1 = await fetch("/api/log?after=" + consoleAfterLog);
      if (r1.ok) {
        const j1 = await r1.json();
        if (typeof j1.next === "number") consoleAfterLog = j1.next;
        if (j1.lines && j1.lines.length) {
          j1.lines.forEach(line => appendConsole(line));
        }
      }

      const r2 = await fetch("/api/events?after=" + consoleAfterEvt);
      if (r2.ok) {
        const j2 = await r2.json();
        if (typeof j2.next === "number") consoleAfterEvt = j2.next;
        if (j2.lines && j2.lines.length) {
          j2.lines.forEach(line => appendConsole(line));
        }
      }
    } catch (e) {
      appendConsole("[poll error] " + e);
    }

    setTimeout(poll, 200);
  }
  poll();
}


function closeConsoleWindow() {
  const ok = window.confirm("Close this console?");
  if (!ok) return;
  appendConsole("Bye!");
  setTimeout(() => window.close(), 200);
}

function runCommandFromInput() {
  const cmd = cmdInput.value.trim();
  if (!cmd) return;

  appendConsole(">>> " + cmd);

  if (cmd === "exit" || cmd === "quit") {
    closeConsoleWindow();
    return;
  }
  runReplCommand(cmd);
  history.push(cmd);
  historyIndex = history.length;
  cmdInput.value = "";
}

runBtn.addEventListener("click", runCommandFromInput);

cmdInput.addEventListener("keydown", (ev) => {
  if (ev.key === "Enter") {
    runCommandFromInput();
    return;
  }

  if (ev.ctrlKey && (ev.key === "d" || ev.key === "D")) {
    ev.preventDefault();
    closeConsoleWindow();
    return;
  }
    
  if (ev.key === "ArrowUp") {
    if (history.length === 0) return;
    historyIndex = Math.max(0, historyIndex - 1);
    cmdInput.value = history[historyIndex] || "";
    ev.preventDefault();
    return;
  }

  if (ev.key === "ArrowDown") {
    if (history.length === 0) return;
    historyIndex = Math.min(history.length, historyIndex + 1);
    cmdInput.value = history[historyIndex] || "";
    if (historyIndex === history.length) cmdInput.value = "";
    ev.preventDefault();
  }
});

function quick(id, cmd) {
  document.getElementById(id).addEventListener("click", () => {
    appendConsole(">>> " + cmd);
    runReplCommand(cmd);
  });
}

quick("btnLoad",    "load src/web_philosophers.abcl");
quick("btnCompile", "compile");
quick("btnStart",   "send table.start();");
quick("btnP0",      "send p0.start();");
quick("btnP1",      "send p1.start();");
quick("btnP2",      "send p2.start();");
quick("btnP3",      "send p3.start();");
quick("btnP4",      "send p4.start();");

document.getElementById("btnViz").addEventListener("click", () => {
  window.open("/viz_philosophers.html", "_blank", "width=1100,height=1050");
});

document.getElementById("btnClear").addEventListener("click", () => {
  consoleOut.textContent = "";
});

appendConsole("AIPL Server Console");
appendConsole("sid=" + sid);
appendConsole("This console talks to /api/repl.");
appendConsole("");

startConsoleStreaming();
