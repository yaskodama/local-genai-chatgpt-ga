document.body.innerHTML = `
<div id="bar" style="padding:10px;background:#222;border-bottom:1px solid #333;">
  <button class="quick" id="btnHello">print hello</button>
  <button class="quick" id="btnCalc">1 + 2</button>
  <button class="quick" id="btnClear">clear</button>
</div>
<div id="consoleOut"
     style="height:calc(100vh - 120px);overflow:auto;padding:12px;white-space:pre-wrap;background:#000;color:#0f0;font-family:monospace;"></div>
<div id="inputRow"
     style="display:flex;gap:8px;padding:10px;background:#181818;border-top:1px solid #333;">
  <input id="cmd" type="text" placeholder="Browser local command"
         style="flex:1;padding:8px;background:#222;color:#fff;border:1px solid #555;">
  <button id="runBtn"
          style="padding:8px 12px;background:#333;color:#fff;border:1px solid #666;cursor:pointer;">Run</button>
</div>
`;

const consoleOut = document.getElementById("consoleOut");
const cmdInput = document.getElementById("cmd");
const runBtn = document.getElementById("runBtn");

let history = [];
let historyIndex = -1;

function appendConsole(line) {
  if (!line) return;
  consoleOut.textContent += line;
  if (!line.endsWith("\n")) consoleOut.textContent += "\n";
  consoleOut.scrollTop = consoleOut.scrollHeight;
}

const BrowserABCL = {
  actors: {},

  print(msg) {
    appendConsole(String(msg));
    return null;
  },

  createActor(name, cls) {
    this.actors[name] = { className: cls, mailbox: [] };
    appendConsole("[actor created] " + name + " : " + cls);
    return name;
  },

  send(name, method, args = []) {
    if (!this.actors[name]) {
      appendConsole("[ERROR] actor not found: " + name);
      return null;
    }
    appendConsole("[send] " + name + "." + method + "(" + args.join(", ") + ")");
    return null;
  },

  help() {
    appendConsole("Available commands/examples:");
    appendConsole('  BrowserABCL.print("hello")');
    appendConsole('  BrowserABCL.createActor("a1","Calc")');
    appendConsole('  BrowserABCL.send("a1","add",[3,4])');
    appendConsole("  1 + 2");
    return null;
  }
};

window.BrowserABCL = BrowserABCL;

function closeConsoleWindow() {
  const ok = window.confirm("Close this console?");
  if (!ok) return;
  appendConsole("Bye!");
  setTimeout(() => window.close(), 200);
}

function runLocal(c) {
  appendConsole(">>> " + c);
  if (c === "exit" || c === "quit") {
    closeConsoleWindow();
    return;
  }
  try {
    const result = eval(c);
    if (result !== undefined && result !== null) {
      appendConsole(String(result));
    }
  } catch (e) {
    appendConsole("[ERROR] " + e);
  }
}

function runCommandFromInput() {
  const cmd = cmdInput.value.trim();
  if (!cmd) return;

  runLocal(cmd);

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

document.getElementById("btnHello").addEventListener("click", () => {
  runLocal('BrowserABCL.print("hello from browser console")');
});

document.getElementById("btnCalc").addEventListener("click", () => {
  runLocal("1 + 2");
});

document.getElementById("btnClear").addEventListener("click", () => {
  consoleOut.textContent = "";
});

appendConsole("AIPL Browser Console");
appendConsole("This is a browser-local console.");
appendConsole("At the moment it runs JavaScript helpers locally.");
appendConsole("Next step: embed a browser-only AIPL interpreter here.");
appendConsole("");
appendConsole('Try: BrowserABCL.help()');
appendConsole("");
