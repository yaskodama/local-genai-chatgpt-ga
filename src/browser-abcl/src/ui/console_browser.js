import * as AST from "../ast.js";
import { Interpreter } from "../interpreter.js";

const SAMPLES = {
  pingpong: `class Pinger {
  method init() {
    print("Pinger starting");
    send ponger.ping();
  }
  method pong() {
    print("Pinger got pong");
    send sender.ping();
  }
}

class Ponger {
  method ping() {
    print("Ponger got ping");
    send sender.pong();
  }
}

var pinger = new Pinger();
var ponger = new Ponger();`,

  calc: `class Calc {
  method init() {
    print("Calc initialized");
  }

  method main() {
    print("waiting...");
    select {
      case add(a,b) -> {
        print("add received");
        reply(a + b);
      }
      timeout 3000 -> {
        print("timeout occurred");
      }
    }
    print("select finished");
  }
}

var calc = new Calc();
send calc.main();
send calc.add(3,4);`,

  rotate4: `class Line {
  var cx = 0.0;
  var cy = 0.0;
  var angle = 0.0;
  var len = 60.0;

  method init(startCx, startCy, startAngle) {
    cx = startCx;
    cy = startCy;
    angle = startAngle;
  }

  method rotate() {
    angle = angle + 3.0;
    var rad = angle * 3.14159 / 180.0;
    var dx = cos(rad) * len;
    var dy = sin(rad) * len;
    var x1 = cx - dx;
    var y1 = cy - dy;
    var x2 = cx + dx;
    var y2 = cy + dy;
    call canvas_line(x1, y1, x2, y2);
    call wait(32);
    send self.rotate();
  }
}

// Square vertices
var li1 = new Line(100.0, 100.0,   0.0);
var li2 = new Line(300.0, 100.0,  90.0);
var li3 = new Line(100.0, 300.0, 180.0);
var li4 = new Line(300.0, 300.0, 270.0);
send li1.rotate();
send li2.rotate();
send li3.rotate();
send li4.rotate();`,

  philosophers: `class Fork {
  var id       = 0;
  var taken    = 0;
  var waiter   = "";
  var waiterId = 0;

  method init(myId) { id = myId; }

  method take(reqId) {
    if (taken == 0) {
      taken = 1;
      call fork_held(id, reqId);
      send sender.fork_granted();
    } else {
      waiter   = sender;
      waiterId = reqId;
    }
  }

  method release() {
    if (waiter == "") {
      taken = 0;
      call fork_free(id);
    } else {
      send waiter.fork_granted();
      call fork_held(id, waiterId);
      waiter = "";
    }
  }
}

class Philosopher {
  var id       = 0;
  var lowFork  = "";
  var highFork = "";
  var hasLow   = 0;
  var eatCount = 0;

  method init(myId, lo, hi) {
    id = myId;
    lowFork  = lo;
    highFork = hi;
    send self.think();
  }

  method think() {
    call philo_state(id, 0);
    call wait(700);
    send self.hungry();
  }

  method hungry() {
    call philo_state(id, 1);
    hasLow = 0;
    send lowFork.take(id);
  }

  method fork_granted() {
    if (hasLow == 0) {
      hasLow = 1;
      send highFork.take(id);
    } else {
      send self.eat();
    }
  }

  method eat() {
    call philo_state(id, 2);
    eatCount = eatCount + 1;
    call wait(900);
    send self.eat_done();
  }

  method eat_done() {
    send lowFork.release();
    send highFork.release();
    send self.think();
  }
}

var fork0 = new Fork(0);
var fork1 = new Fork(1);
var fork2 = new Fork(2);
var fork3 = new Fork(3);
var fork4 = new Fork(4);

var p0 = new Philosopher(0, fork0, fork4);
var p1 = new Philosopher(1, fork0, fork1);
var p2 = new Philosopher(2, fork1, fork2);
var p3 = new Philosopher(3, fork2, fork3);
var p4 = new Philosopher(4, fork3, fork4);`,

  bounded_buffer: `class Buffer {
  var cap   = 4;
  var s0    = 0;
  var s1    = 0;
  var s2    = 0;
  var s3    = 0;
  var head  = 0;
  var tail  = 0;
  var count = 0;

  var pwaiter = "";
  var pitem   = 0;
  var cwaiter = "";

  method put(item) {
    if (cwaiter != "") {
      send sender.put_ok();
      send cwaiter.got(item);
      print("[BUF] passthrough put=" + item);
      cwaiter = "";
    } else {
      if (count == cap) {
        pwaiter = sender;
        pitem   = item;
        print("[BUF] FULL  -- queued put=" + item);
      } else {
        if (tail == 0) { s0 = item; }
        if (tail == 1) { s1 = item; }
        if (tail == 2) { s2 = item; }
        if (tail == 3) { s3 = item; }
        tail = tail + 1;
        if (tail == cap) { tail = 0; }
        count = count + 1;
        print("[BUF] put=" + item + "   count=" + count);
        send sender.put_ok();
      }
    }
  }

  method get() {
    if (count == 0) {
      cwaiter = sender;
      print("[BUF] EMPTY -- queued get");
    } else {
      if (head == 0) { send sender.got(s0); }
      if (head == 1) { send sender.got(s1); }
      if (head == 2) { send sender.got(s2); }
      if (head == 3) { send sender.got(s3); }
      head = head + 1;
      if (head == cap) { head = 0; }
      count = count - 1;
      print("[BUF] get   count=" + count);
      if (pwaiter != "") {
        if (tail == 0) { s0 = pitem; }
        if (tail == 1) { s1 = pitem; }
        if (tail == 2) { s2 = pitem; }
        if (tail == 3) { s3 = pitem; }
        tail = tail + 1;
        if (tail == cap) { tail = 0; }
        count = count + 1;
        print("[BUF] accepted queued put=" + pitem);
        send pwaiter.put_ok();
        pwaiter = "";
      }
    }
  }
}

class Producer {
  var id  = 0;
  var buf = "";
  var n   = 0;
  var max = 0;

  method init(myId, b, limit) {
    id = myId; buf = b; max = limit;
    send self.produce();
  }

  method produce() {
    if (n == max) {
      print("[P" + id + "] DONE");
    } else {
      n = n + 1;
      print("[P" + id + "] -> put " + n);
      send buf.put(n);
    }
  }

  method put_ok() {
    call wait(120);
    send self.produce();
  }
}

class Consumer {
  var id    = 0;
  var buf   = "";
  var taken = 0;
  var max   = 0;

  method init(myId, b, limit) {
    id = myId; buf = b; max = limit;
    send buf.get();
  }

  method got(item) {
    taken = taken + 1;
    print("[C" + id + "] got " + item + "   (total=" + taken + ")");
    if (taken == max) {
      print("[C" + id + "] DONE");
    } else {
      call wait(420);
      send self.do_get();
    }
  }

  method do_get() {
    send buf.get();
  }
}

var buf = new Buffer();
var p0  = new Producer(0, buf, 12);
var c0  = new Consumer(0, buf, 12);`,
};

window.addEventListener("DOMContentLoaded", () => {
  const parser = window.parser;

  document.body.innerHTML = `
    <div id="bar" style="padding:10px;background:#222;border-bottom:1px solid #333;display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
      <button id="btnRun">▶ run</button>
      <button id="btnStop">■ stop</button>
      <button id="btnParseOnly">parse only</button>
      <button id="btnClear">clear</button>
      <span style="color:#888;margin-left:8px;">sample:</span>
      <button id="btnLoadPingPong">PingPong</button>
      <button id="btnLoadCalc">Calc (select)</button>
      <button id="btnLoadRotate">Rotate4Lines</button>
      <button id="btnLoadPhilos">5 Philosophers</button>
      <button id="btnLoadBuf">Bounded Buffer</button>
    </div>

    <div style="display:flex;height:calc(100vh - 360px);min-height:160px;">
      <div id="consoleOut"
           style="flex:1;overflow:auto;padding:12px;white-space:pre-wrap;
                  background:#000;color:#0f0;font-family:monospace;"></div>
      <canvas id="canvas" width="500" height="500"
              style="background:#0a0a1a;border-left:1px solid #333;flex-shrink:0;"></canvas>
    </div>

    <div id="inputRow"
         style="display:flex;gap:8px;align-items:center;padding:10px;
                background:#181818;border-top:1px solid #333;">
      <span style="color:#0f0;font-family:monospace;font-weight:bold;">ABCL/c+&gt;</span>
      <input id="cmd" type="text" placeholder="single command"
             style="flex:1;padding:8px;background:#222;color:#fff;border:1px solid #555;font-family:monospace;">
      <button id="runCmdBtn"
              style="padding:8px 12px;background:#333;color:#fff;border:1px solid #666;cursor:pointer;">Run</button>
    </div>

    <textarea id="src"
              style="width:100%;height:180px;background:#111;color:#fff;
                     font-family:monospace;padding:8px;box-sizing:border-box;">${SAMPLES.pingpong}</textarea>
  `;

  const consoleOut = document.getElementById("consoleOut");
  const canvas     = document.getElementById("canvas");
  const src        = document.getElementById("src");
  const cmdInput   = document.getElementById("cmd");

  let history = [], historyIndex = -1;
  let activeTimers = [];
  let running = false;

  // Wrap setTimeout so we can cancel all actor threads on Stop
  const _origSetTimeout = window.setTimeout.bind(window);
  window.setTimeout = function(fn, ms, ...rest) {
    const id = _origSetTimeout(fn, ms, ...rest);
    if (running) activeTimers.push(id);
    return id;
  };

  function stopAll() {
    running = false;
    activeTimers.forEach(id => clearTimeout(id));
    activeTimers = [];
  }

  function appendConsole(line) {
    if (line === undefined || line === null) return;
    const s = String(line);
    consoleOut.textContent += s;
    if (!s.endsWith("\n")) consoleOut.textContent += "\n";
    consoleOut.scrollTop = consoleOut.scrollHeight;
  }

  function clearConsole() { consoleOut.textContent = ""; }

  function closeConsoleWindow() {
    if (!window.confirm("Close this console?")) return;
    appendConsole("Bye!");
    setTimeout(() => window.close(), 200);
  }

  if (!parser) {
    appendConsole("[ERROR] window.parser is not available.");
    return;
  }
  parser.yy = AST;

  function makeInterpreter() {
    const interp = new Interpreter(appendConsole);
    interp.setCanvas(canvas);
    return interp;
  }

  function runSource(code) {
    stopAll();
    clearConsole();
    appendConsole(">>> run");
    running = true;
    try {
      const ast = parser.parse(code);
      appendConsole("[parse ok]");
      makeInterpreter().runProgram(ast);
    } catch (e) {
      running = false;
      appendConsole("[ERROR] " + e);
    }
  }

  function parseOnly(code) {
    stopAll();
    clearConsole();
    appendConsole(">>> parse");
    try {
      const ast = parser.parse(code);
      appendConsole("[parse ok]");
      appendConsole(JSON.stringify(ast, null, 2));
    } catch (e) {
      appendConsole("[ERROR] " + e);
    }
  }

  function runSingleCommand(cmd) {
    const trimmed = cmd.trim();
    if (!trimmed) return;

    if (trimmed === "exit" || trimmed === "quit") { closeConsoleWindow(); return; }
    if (trimmed === "help") {
      appendConsole("Commands: help, exit, stop");
      appendConsole("Or type any ABCL/c+ statement.");
      return;
    }
    if (trimmed === "stop") { stopAll(); appendConsole("[stopped]"); return; }

    appendConsole("ABCL/c+> " + trimmed);
    try {
      const wrapped = trimmed.endsWith(";") ? trimmed : trimmed + ";";
      const ast = parser.parse(wrapped);
      appendConsole("[parse ok]");
      running = true;
      makeInterpreter().runProgram(ast);
    } catch (e) {
      running = false;
      appendConsole("[ERROR] " + e);
    }
  }

  document.getElementById("btnRun").addEventListener("click", () => runSource(src.value));
  document.getElementById("btnStop").addEventListener("click", () => { stopAll(); appendConsole("[stopped]"); });
  document.getElementById("btnParseOnly").addEventListener("click", () => parseOnly(src.value));
  document.getElementById("btnClear").addEventListener("click", () => { clearConsole(); cmdInput.focus(); });
  document.getElementById("btnLoadPingPong").addEventListener("click", () => { src.value = SAMPLES.pingpong; });
  document.getElementById("btnLoadCalc").addEventListener("click", () => { src.value = SAMPLES.calc; });
  document.getElementById("btnLoadRotate").addEventListener("click", () => { src.value = SAMPLES.rotate4; });
  document.getElementById("btnLoadPhilos").addEventListener("click", () => { src.value = SAMPLES.philosophers; });
  document.getElementById("btnLoadBuf").addEventListener("click", () => { src.value = SAMPLES.bounded_buffer; });

  document.getElementById("runCmdBtn").addEventListener("click", () => {
    const cmd = cmdInput.value.trim();
    if (!cmd) return;
    history.push(cmd); historyIndex = history.length;
    runSingleCommand(cmd);
    cmdInput.value = ""; cmdInput.focus();
  });

  cmdInput.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") { document.getElementById("runCmdBtn").click(); return; }
    if (ev.ctrlKey && (ev.key === "d" || ev.key === "D")) { ev.preventDefault(); closeConsoleWindow(); return; }
    if (ev.key === "ArrowUp") {
      if (!history.length) return;
      historyIndex = Math.max(0, historyIndex - 1);
      cmdInput.value = history[historyIndex] || ""; ev.preventDefault();
    }
    if (ev.key === "ArrowDown") {
      if (!history.length) return;
      historyIndex = Math.min(history.length, historyIndex + 1);
      cmdInput.value = historyIndex === history.length ? "" : history[historyIndex];
      ev.preventDefault();
    }
  });

  appendConsole("ABCL/c+ Browser Console — actor threads edition");
  appendConsole("Each actor runs as an independent setTimeout thread.");
  appendConsole("");
  appendConsole("Samples: PingPong / Calc(select) / Rotate4Lines / 5 Philosophers / Bounded Buffer");
  appendConsole("Demos:   /rotate4lines.html  /philosophers.html  /bounded_buffer.html");
  appendConsole("Press ▶ run to execute.");
  appendConsole("");
  cmdInput.focus();
});
