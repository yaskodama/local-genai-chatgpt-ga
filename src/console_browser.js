document.body.innerHTML = `
<div id="bar" style="padding:10px;background:#222;border-bottom:1px solid #333;">
  <button class="quick" id="btnLoadSample">load sample</button>
  <button class="quick" id="btnRunSample">run sample</button>
  <button class="quick" id="btnClear">clear</button>
</div>
<div id="consoleOut"
     style="height:calc(100vh - 120px);overflow:auto;padding:12px;white-space:pre-wrap;background:#000;color:#0f0;font-family:monospace;"></div>
<div id="inputRow" style="display:flex;gap:8px;padding:10px;background:#181818;border-top:1px solid #333;">
  <input id="cmd" type="text" placeholder="Browser AIPL command"
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
  if (line === undefined || line === null) return;
  consoleOut.textContent += String(line);
  if (!String(line).endsWith("\n")) consoleOut.textContent += "\n";
  consoleOut.scrollTop = consoleOut.scrollHeight;
}

function closeConsoleWindow() {
  const ok = window.confirm("Close this console?");
  if (!ok) return;
  appendConsole("Bye!");
  setTimeout(() => window.close(), 200);
}

/* =========================================================
   Minimal Browser-only AIPL runtime
   ========================================================= */

class BrowserABCLRuntime {
  constructor(printer) {
    this.print = printer;
    this.classes = new Map();  // className -> { methods: Map }
    this.actors = new Map();   // actorName -> actor object
    this.nextActorId = 1;
    this.replyBuffer = [];
  }

  reset() {
    this.classes.clear();
    this.actors.clear();
    this.nextActorId = 1;
    this.replyBuffer = [];
  }

  tokenizeArgs(argText) {
    const s = argText.trim();
    if (!s) return [];
    const parts = [];
    let current = "";
    let inString = false;
    let quote = null;
    let depth = 0;

    for (let i = 0; i < s.length; i++) {
      const ch = s[i];
      if (inString) {
        current += ch;
        if (ch === quote && s[i - 1] !== "\\") {
          inString = false;
          quote = null;
        }
        continue;
      }
      if (ch === '"' || ch === "'") {
        inString = true;
        quote = ch;
        current += ch;
        continue;
      }
      if (ch === "(") {
        depth++;
        current += ch;
        continue;
      }
      if (ch === ")") {
        depth--;
        current += ch;
        continue;
      }
      if (ch === "," && depth === 0) {
        parts.push(current.trim());
        current = "";
        continue;
      }
      current += ch;
    }

    if (current.trim() !== "") parts.push(current.trim());
    return parts;
  }
    
  parseAtom(text, env = {}) {
    const s = text.trim();
    if (s in env) return env[s];
    if ((s.startsWith('"') && s.endsWith('"')) || (s.startsWith("'") && s.endsWith("'"))) {
      return s.substring(1, s.length - 1);
    }
    if (/^-?\d+$/.test(s)) return parseInt(s, 10);
    if (/^-?\d+\.\d+$/.test(s)) return parseFloat(s);
    if (s === "true") return true;
    if (s === "false") return false;
    if (s === "null") return null;
    return s;
  }

  evalSimpleExpr(expr, env = {}) {
    const s = expr.trim();
    if (s.includes("+")) {
      const parts = s.split("+").map(x => x.trim());
      const vals = parts.map(p => this.parseAtom(p, env));
      return vals.reduce((a, b) => a + b);
    }
    return this.parseAtom(s, env);
  }

  loadProgram(source) {
    // Very small parser for:
    // class X { method m(a,b) { ... } method init() { ... } }
    const classRegex = /class\s+([A-Za-z_][A-Za-z0-9_]*)\s*\{([\s\S]*?)\}/g;
    let classMatchFound = false;
    for (const match of source.matchAll(classRegex)) {
      classMatchFound = true;
      const className = match[1];
      const classBody = match[2];
      const methods = new Map();
      const methodRegex = /method\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)\s*\{([\s\S]*?)\}/g;
      for (const mm of classBody.matchAll(methodRegex)) {
        const mname = mm[1];
        const params = mm[2].trim() === "" ? [] : mm[2].split(",").map(x => x.trim());
        const body = mm[3].trim();
        methods.set(mname, { params, body });
      }

      this.classes.set(className, { name: className, methods });
    }
    if (!classMatchFound) {
      throw new Error("No class declarations found");
    }
    return "[Loaded browser ABCL program]";
  }

  createActor(varName, className) {
    const cls = this.classes.get(className);
    if (!cls) throw new Error("Class not found: " + className);

    const actor = {
      name: varName || ("actor" + this.nextActorId++),
      className,
      methods: cls.methods,
      mailbox: [],
      fields: {},
      lastReply: null
    };
    this.actors.set(actor.name, actor);
    this.print("[actor created] " + actor.name + " : " + className);

    if (actor.methods.has("init")) {
      this.invokeMethod(actor, "init", []);
    }
    return actor.name;
  }
    
  send(actorName, methodName, args, unsafe = false) {
    const actor = this.actors.get(actorName);
    if (!actor) throw new Error("actor not found: " + actorName);

    if (!unsafe && !actor.methods.has(methodName)) {
      throw new Error("unknown method: " + actor.className + "." + methodName);
    }
    actor.mailbox.push({ methodName, args });
    this.print("[send] " + actorName + "." + methodName + "(" + args.join(", ") + ")");
    this.processMailbox(actor);
    return null;
  }

  processMailbox(actor) {
    while (actor.mailbox.length > 0) {
      const msg = actor.mailbox.shift();
      this.invokeMethod(actor, msg.methodName, msg.args);
    }
  }

  invokeMethod(actor, methodName, args) {
    const method = actor.methods.get(methodName);
    if (!method) {
      this.print("[ERROR] unknown method at runtime: " + actor.className + "." + methodName);
      return null;
    }

      const env = {};
      method.params.forEach((p, i) => {
        env[p] = args[i];
      });

      const lines = method.body
      .split(";")
      .map(x => x.trim())
      .filter(x => x.length > 0);

      let lastValue = null;

    for (const line of lines) {
      if (line.startsWith("print(") && line.endsWith(")")) {
        const inner = line.slice(6, -1);
        const v = this.evalSimpleExpr(inner, env);
        this.print(v);
        lastValue = v;
        continue;
      }

      if (line.startsWith("reply(") && line.endsWith(")")) {
        const inner = line.slice(6, -1);
        const v = this.evalSimpleExpr(inner, env);
        actor.lastReply = v;
        this.replyBuffer.push(v);
        this.print("[REPLY] value=" + v);
        lastValue = v;
        continue;
      }

      if (line.startsWith("send! ")) {
        const rest = line.slice(6).trim();
        this.evalSendStatement(rest, true);
        continue;
      }
      
      if (line.startsWith("send ")) {
        const rest = line.slice(5).trim();
        this.evalSendStatement(rest, false);
        continue;
      }

      // simple assignment: x = expr
      const assignMatch = line.match(/^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)$/);
      if (assignMatch) {
        const name = assignMatch[1];
        const rhs = assignMatch[2];
        env[name] = this.evalSimpleExpr(rhs, env);
        lastValue = env[name];
        continue;
      }
      this.print("[WARN] unsupported statement: " + line);
    }
    return lastValue;
  }

evalSendStatement(stmt, unsafe = false) {
    // target.method(args)
    const m = stmt.match(/^([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\((.*)\)$/);
    if (!m) throw new Error("bad send syntax: " + stmt);

    const actorName = m[1];
    const methodName = m[2];
    const args = this.tokenizeArgs(m[3]).map(x => this.evalSimpleExpr(x, {}));
    return this.send(actorName, methodName, args, unsafe);
}

execute(command) {
    const cmd = command.trim();

    if (cmd === "") return null;

    if (cmd === "reset") {
      this.reset();
      return "[runtime reset]";
    }

    if (cmd.startsWith("class ")) {
      return this.loadProgram(cmd);
    }

    const varNewMatch = cmd.match(/^var\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*new\s+([A-Za-z_][A-Za-z0-9_]*)\(\)\s*;?$/);
    if (varNewMatch) {
      const varName = varNewMatch[1];
      const className = varNewMatch[2];
      return this.createActor(varName, className);
    }

    const sendBangMatch = cmd.match(/^send!\s+(.+);?$/);
    if (sendBangMatch) {
      return this.evalSendStatement(sendBangMatch[1], true);
    }

    const sendMatch = cmd.match(/^send\s+(.+);?$/);
    if (sendMatch) {
      return this.evalSendStatement(sendMatch[1], false);
    }
     
    if (cmd.startsWith("print(") && cmd.endsWith(")")) {
      const inner = cmd.slice(6, -1);
      const v = this.evalSimpleExpr(inner, {});
      this.print(v);
      return v;
    }

    throw new Error("unsupported command: " + cmd);
  }

  help() {
    return [
      'Supported commands:',
      '  class Calc { method init() { print("hi"); } method add(a,b) { reply(a + b); } }',
      '  var c = new Calc();',
      '  send c.add(3,4);',
      '  send! c.unknown(1);',
      '  print("hello");',
      '  reset'
    ].join("\n");
  }
}

const runtime = new BrowserABCLRuntime(appendConsole);

function runLocal(cmd) {
  appendConsole(">>> " + cmd);

  if (cmd === "exit" || cmd === "quit") {
    closeConsoleWindow();
    return;
  }

  if (cmd === "help") {
    appendConsole(runtime.help());
    return;
  }

  try {
    const result = runtime.execute(cmd);
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

document.getElementById("btnLoadSample").addEventListener("click", () => {
  const sample = `class Calc {
  method init() { print("Calc initialized"); }
  method add(a,b) { print("add received"); reply(a + b); }
}`;
  appendConsole(">>> load sample");
  try {
    const r = runtime.loadProgram(sample);
    appendConsole(r);
  } catch (e) {
    appendConsole("[ERROR] " + e);
  }
});

document.getElementById("btnRunSample").addEventListener("click", () => {
  runLocal("var calc = new Calc();");
  runLocal("send calc.add(3,4);");
});

document.getElementById("btnClear").addEventListener("click", () => {
  consoleOut.textContent = "";
});

appendConsole("AIPL Browser Console");
appendConsole("This is phase 1 of a browser-only AIPL interpreter.");
appendConsole("Available now: class / method / var / new / send / send! / print / reply");
appendConsole('Try: help');
appendConsole("");
