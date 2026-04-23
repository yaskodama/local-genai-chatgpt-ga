(function () {
  const canvas    = document.getElementById("canvas");
  const ctx       = canvas.getContext("2d");
  const srcText   = document.getElementById("srcText");
  const statusBox = document.getElementById("status");
  const logBox    = document.getElementById("logBox");
  const btnLoad    = document.getElementById("btnLoad");
  const btnCompile = document.getElementById("btnCompile");
  const btnStart   = document.getElementById("btnStart");
  const btnStop    = document.getElementById("btnStop");
  const btnReset   = document.getElementById("btnReset");

  const W = canvas.width, H = canvas.height;
  const CX = W / 2, CY = H / 2;
  const R  = Math.min(W, H) * 0.32;
  const N = 5;

  const STATE_IDLE   = -1;
  const STATE_THINK  = 0;
  const STATE_HUNGRY = 1;
  const STATE_EAT    = 2;
  const STATE_DONE   = 3;

  // Match browser-abcl/src/runtime.js palette so the two visualizations look
  // the same.
  const PHILO_COLORS = ["#ff5566", "#ffa833", "#3ddc6e", "#3aa8ff", "#c765ff"];
  const STATE_NAME   = ["THINK", "HUNGRY", "EAT"];
  const STATE_INNER  = ["#334",  "#ffcc40", "#40e070"];

  const philoState = [STATE_IDLE, STATE_IDLE, STATE_IDLE, STATE_IDLE, STATE_IDLE];
  const philoEat   = [0, 0, 0, 0, 0];
  const forkTaken  = [0, 0, 0, 0, 0];
  const forkHolder = [-1, -1, -1, -1, -1];

  // Philosopher positions on a pentagon ring (P0 at top, clockwise).
  const philoPos = [];
  for (let i = 0; i < N; i++) {
    const theta = -Math.PI / 2 + (i * 2 * Math.PI / N);
    philoPos.push({ x: CX + R * Math.cos(theta), y: CY + R * Math.sin(theta) });
  }

  // Fork i sits between philosopher i and philosopher (i+1)%N
  // (matches viz_philosophers.abcl: P0 uses fork0 & fork4, P1 uses fork0 & fork1, ...).
  const forkPos = [];
  for (let i = 0; i < N; i++) {
    const a = philoPos[i], b = philoPos[(i + 1) % N];
    const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
    const ex = b.x - a.x, ey = b.y - a.y;
    const elen = Math.hypot(ex, ey) || 1;
    forkPos.push({ x: mx, y: my, tx: ex / elen, ty: ey / elen });
  }

  function drawTable() {
    ctx.fillStyle = "#0a0a1a";
    ctx.fillRect(0, 0, W, H);

    // Pentagon table outline
    ctx.strokeStyle = "#262640";
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let i = 0; i < N; i++) {
      const p = philoPos[i];
      if (i === 0) ctx.moveTo(p.x, p.y);
      else         ctx.lineTo(p.x, p.y);
    }
    ctx.closePath();
    ctx.stroke();
  }

  function drawFork(i) {
    const fp = forkPos[i];
    const restX = fp.x, restY = fp.y;
    const held = forkTaken[i] === 1 && forkHolder[i] >= 0;

    if (!held) {
      // FREE — short tangent line at edge midpoint
      const tx = fp.tx, ty = fp.ty;
      ctx.strokeStyle = "#7a7aa0";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(restX - tx * 13, restY - ty * 13);
      ctx.lineTo(restX + tx * 13, restY + ty * 13);
      ctx.stroke();

      const cdx = CX - restX, cdy = CY - restY;
      const clen = Math.hypot(cdx, cdy) || 1;
      ctx.fillStyle = "#9a9abc";
      ctx.font = "10px monospace";
      ctx.textAlign = "center";
      ctx.fillText("F" + i, restX + (cdx / clen) * 14, restY + (cdy / clen) * 14);
      return;
    }

    // HELD — translate 50% toward holder, draw perpendicular bar + arrow
    const holder = philoPos[forkHolder[i]];
    const dx = holder.x - restX, dy = holder.y - restY;
    const dist = Math.hypot(dx, dy) || 1;
    const ux = dx / dist, uy = dy / dist;

    const forkX = restX + ux * dist * 0.50;
    const forkY = restY + uy * dist * 0.50;
    const color = PHILO_COLORS[forkHolder[i]];

    // Fork bar — perpendicular to (rest → holder)
    const px = -uy, py = ux;
    ctx.strokeStyle = color;
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(forkX - px * 9, forkY - py * 9);
    ctx.lineTo(forkX + px * 9, forkY + py * 9);
    ctx.stroke();

    // Arrow shaft
    const shaftStartX = forkX + ux * 5;
    const shaftStartY = forkY + uy * 5;
    const shaftEndX   = holder.x - ux * 28;
    const shaftEndY   = holder.y - uy * 28;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(shaftStartX, shaftStartY);
    ctx.lineTo(shaftEndX, shaftEndY);
    ctx.stroke();

    // Arrowhead
    const ah = 9;
    const ang = Math.atan2(shaftEndY - shaftStartY, shaftEndX - shaftStartX);
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.moveTo(shaftEndX, shaftEndY);
    ctx.lineTo(shaftEndX - ah * Math.cos(ang - Math.PI / 6),
               shaftEndY - ah * Math.sin(ang - Math.PI / 6));
    ctx.lineTo(shaftEndX - ah * Math.cos(ang + Math.PI / 6),
               shaftEndY - ah * Math.sin(ang + Math.PI / 6));
    ctx.closePath();
    ctx.fill();

    // Fork label at rest position
    const cdx = CX - restX, cdy = CY - restY;
    const clen = Math.hypot(cdx, cdy) || 1;
    ctx.fillStyle = color;
    ctx.font = "10px monospace";
    ctx.textAlign = "center";
    ctx.fillText("F" + i, restX + (cdx / clen) * 14, restY + (cdy / clen) * 14);
  }

  function drawPhilo(i) {
    const p = philoPos[i];
    const st = philoState[i];
    const base = PHILO_COLORS[i];

    // Outer ring — philosopher's base color; thicker when eating
    ctx.strokeStyle = base;
    ctx.lineWidth = (st === STATE_EAT) ? 3 : (st === STATE_HUNGRY ? 2 : 1);
    ctx.beginPath();
    ctx.arc(p.x, p.y, 24, 0, 2 * Math.PI);
    ctx.stroke();

    // Inner state dot
    if (st === STATE_IDLE) {
      // no fill — idle marker
    } else if (st === STATE_DONE) {
      ctx.fillStyle = "#666";
      ctx.beginPath();
      ctx.arc(p.x, p.y, 6, 0, 2 * Math.PI);
      ctx.fill();
    } else {
      ctx.fillStyle = STATE_INNER[st];
      ctx.beginPath();
      ctx.arc(p.x, p.y, st === STATE_EAT ? 11 : 6, 0, 2 * Math.PI);
      ctx.fill();
    }

    // Labels
    ctx.fillStyle = base;
    ctx.font = "bold 14px monospace";
    ctx.textAlign = "center";
    ctx.fillText("P" + i, p.x, p.y + 5);
    ctx.font = "10px monospace";
    const label = (st === STATE_IDLE) ? "idle"
                : (st === STATE_DONE) ? "done"
                : STATE_NAME[st];
    ctx.fillText(label, p.x, p.y + 42);
    ctx.fillText("eat:" + philoEat[i], p.x, p.y + 56);
  }

  function draw() {
    drawTable();
    for (let i = 0; i < N; i++) drawFork(i);
    for (let i = 0; i < N; i++) drawPhilo(i);
  }

  function appendLog(line) {
    const max = 600;
    logBox.textContent += line + "\n";
    if (logBox.textContent.length > max * 200) {
      logBox.textContent = logBox.textContent.slice(-max * 200);
    }
    logBox.scrollTop = logBox.scrollHeight;
  }

  function handleLine(line) {
    let m = line.match(/^VIZ\s+PHILO\s+(\d+)\s+(THINK|HUNGRY|EAT|DONE)(?:\s+(\d+))?/);
    if (m) {
      const id = +m[1];
      if (id < 0 || id >= N) return false;
      switch (m[2]) {
        case "THINK":  philoState[id] = STATE_THINK;  break;
        case "HUNGRY": philoState[id] = STATE_HUNGRY; break;
        case "EAT":
          philoState[id] = STATE_EAT;
          if (m[3]) philoEat[id] = +m[3];
          break;
        case "DONE":   philoState[id] = STATE_DONE;   break;
      }
      return true;
    }
    m = line.match(/^VIZ\s+FORK\s+(\d+)\s+(FREE|TAKEN|HANDOFF)(?:\s+(\d+))?/);
    if (m) {
      const id = +m[1];
      if (id < 0 || id >= N) return false;
      switch (m[2]) {
        case "FREE":
          forkTaken[id] = 0;
          forkHolder[id] = -1;
          break;
        case "TAKEN":
          forkTaken[id] = 1;
          forkHolder[id] = m[3] ? +m[3] : -1;
          break;
        case "HANDOFF":
          forkTaken[id] = 1;
          break;
      }
      return true;
    }
    return false;
  }

  let afterLog = -1;
  async function poll() {
    try {
      const r = await fetch("/api/log?after=" + afterLog);
      if (r.ok) {
        const j = await r.json();
        if (typeof j.next === "number") afterLog = j.next;
        if (j.lines && j.lines.length) {
          let dirty = false;
          for (const line of j.lines) {
            if (handleLine(line)) {
              dirty = true;
              appendLog(line);
            }
          }
          if (dirty) draw();
        }
      }
    } catch (e) {
      // ignore transient polling errors
    }
    setTimeout(poll, 200);
  }

  async function loadSource() {
    try {
      const r = await fetch("/viz_philosophers.abcl");
      if (r.ok) srcText.textContent = await r.text();
      else srcText.textContent = "(failed to load: " + r.status + ")";
    } catch (e) {
      srcText.textContent = "(load error: " + e + ")";
    }
  }

  async function runRepl(cmd) {
    statusBox.textContent = "→ " + cmd;
    try {
      const r = await fetch("/api/repl", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sid: "viz", command: cmd })
      });
      const t = await r.text();
      statusBox.textContent = "done: " + cmd + (t.trim() ? " [" + t.trim().slice(0, 60) + "]" : "");
    } catch (e) {
      statusBox.textContent = "error: " + e;
    }
  }

  function resetDisplay() {
    for (let i = 0; i < N; i++) {
      philoState[i]  = STATE_IDLE;
      philoEat[i]    = 0;
      forkTaken[i]   = 0;
      forkHolder[i]  = -1;
    }
    logBox.textContent = "";
    draw();
    statusBox.textContent = "display reset";
  }

  btnLoad   .addEventListener("click", () => runRepl("load src/viz_philosophers.abcl"));
  btnCompile.addEventListener("click", () => runRepl("compile"));
  btnStart  .addEventListener("click", () => runRepl("send table.start();"));
  btnStop   .addEventListener("click", () => runRepl("send table.stop();"));
  btnReset  .addEventListener("click", resetDisplay);

  loadSource();
  draw();
  poll();
})();
