// Actor color palette for canvas drawing
const ACTOR_COLORS = ["#ff6060", "#60ff60", "#6090ff", "#ffcc00", "#ff60ff", "#60ffff"];

export class Runtime {
  constructor(printer = console.log) {
    this.print = printer;
    this.classes = new Map();
    this.actors = new Map();
    this.nextId = 1;
    this.replies = [];
    this.canvas = null;        // set externally for canvas output
    this.scene = new Map();    // actorName → {x1,y1,x2,y2,color}   (for rotating lines)
    this.philoStates = new Map(); // id → 0(think)/1(hungry)/2(eat) (for philosophers)
    this.forkStates  = new Map(); // id → 0(free)/1(taken)
    this.forkHolders = new Map(); // id → holding philosopher id (absent when free)
    this._colorIdx = 0;
    this._actorColors = new Map();
    // Drone simulator world state
    this.droneWorld = null;         // {W,H,commRange,viewRange,obstacles:[],safeZone,start}
    this.droneActorById = new Map();   // droneId → actorName
    this.dronePositions = new Map();   // droneId → {x,y}
    this.droneStates    = new Map();   // droneId → 0(flying)/1(arrived)/2(dead)
    this.droneKnowledge = new Map();   // droneId → Set of known obstacle ids

    // ---- Reply slots for now / future / await -----------------------
    // JS is single-threaded, so `now`/`await` need a synchronous "drain":
    // we keep processing actor mailboxes one message at a time until the
    // target slot is fulfilled by some actor's reply().
    this.replySlots = new Map();         // slotId → { fulfilled, value }
    this._nextSlotId = 1;

    // ---- Bounded buffer visualization state -------------------------
    this.bufState = null;                // null until `call buf_init(cap);`

    // ---- Slider-driven runtime variables ----------------------------
    // Read by AIPL programs via the prod_speed() / cons_speed()
    // builtins. The console UI binds sliders to these fields so timings
    // can be tuned live without re-running the program.
    this._prodSpeed = 120;
    this._consSpeed = 420;

    // ---- AIOS coordination + protocol traces ------------------------
    this._aiosServices = new Map();   // alias → actor name
    this._aiosEvents   = [];
    this._protoDefs    = new Map();   // name → ["a.m", ...]
    this._protoActive  = new Map();   // sid → {name, idx, ended}
    this._protoEvents  = [];
    this._protoSeq     = 0;
  }

  setCanvas(canvas) {
    this.canvas = canvas;
  }

  reset() {
    this.classes.clear();
    this.actors.clear();
    this.nextId = 1;
    this.replies = [];
    this.replySlots.clear();
    this._nextSlotId = 1;
    this.scene.clear();
    this.philoStates.clear();
    this.forkStates.clear();
    this.forkHolders.clear();
    this._colorIdx = 0;
    this._actorColors.clear();
    this.droneWorld = null;
    this.droneActorById.clear();
    this.dronePositions.clear();
    this.droneStates.clear();
    this.droneKnowledge.clear();
    this.bufState = null;
    this._aiosServices.clear();
    this._aiosEvents.length = 0;
    this._protoDefs.clear();
    this._protoActive.clear();
    this._protoEvents.length = 0;
    this._protoSeq = 0;
    if (this.canvas) {
      const ctx = this.canvas.getContext("2d");
      ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    }
  }

  registerClass(cls) {
    this.classes.set(cls.name, cls);
  }

  createActor(name, className, initArgs = []) {
    const cls = this.classes.get(className);
    if (!cls) throw new Error("Class not found: " + className);

    // Evaluate class field defaults to initialise actor state
    const state = {};
    for (const field of (cls.fields || [])) {
      state[field.name] = this._evalFieldExpr(field.expr);
    }

    const actor = {
      name,
      className,
      methods: new Map(cls.methods.map(m => [m.name, m])),
      mailbox: [],
      state,
      processing: false,
      scheduled: false,
      __nextDelay: 0,
    };

    this.actors.set(name, actor);
    this.print(`[actor created] ${name} : ${className}`);

    // Queue init — deferred so all actors exist before any init runs
    if (actor.methods.has("init")) {
      actor.mailbox.push({ methodName: "init", args: initArgs, unsafe: false, senderName: null });
      // Auto-schedule when the actor is created mid-run (e.g. spawned from
      // another actor's method). Top-level creation is still batched via
      // scheduleAllActors() after the program body finishes.
      this.scheduleActor(actor);
    }

    return actor;
  }

  // Simple expression evaluator for class field default values (no env needed)
  _evalFieldExpr(expr) {
    if (!expr) return null;
    if (expr.type === "IntLit")   return expr.value;
    if (expr.type === "FloatLit") return expr.value;
    if (expr.type === "StringLit") return expr.value;
    if (expr.type === "Binop") {
      const l = this._evalFieldExpr(expr.left);
      const r = this._evalFieldExpr(expr.right);
      switch (expr.op) {
        case "+": return l + r;
        case "-": return l - r;
        case "*": return l * r;
        case "/": return l / r;
      }
    }
    return 0;
  }

  hasSelectableMethod(actor, methodName) {
    for (const method of actor.methods.values()) {
      if (!method.body || !method.body.statements) continue;
      for (const st of method.body.statements) {
        if (st.type === "Select") {
          for (const c of st.cases) {
            if (c.method === methodName) return true;
          }
        }
      }
    }
    return false;
  }

  knowsMessage(actor, methodName) {
    return actor.methods.has(methodName) || this.hasSelectableMethod(actor, methodName);
  }

  // Enqueue a message — never dispatches synchronously (actor threads handle it).
  // slotId (optional) lets `now`/`future` correlate the reply back to a caller.
  send(actorName, methodName, args, unsafe = false, senderName = null, slotId = null) {
    const actor = this.actors.get(actorName);
    if (!actor) {
      if (unsafe) return;
      throw new Error("actor not found: " + actorName);
    }
    if (!unsafe && !this.knowsMessage(actor, methodName)) {
      throw new Error(`unknown method: ${actor.className}.${methodName}`);
    }
    actor.mailbox.push({ methodName, args, unsafe, senderName, slotId });
    this.print(`[send] ${actorName}.${methodName}(${args.join(", ")})`);
    // Only schedule if not currently inside this actor's invoke
    if (!actor.processing) this.scheduleActor(actor);
  }

  // ---- Reply slot helpers (for now / future / await) ----------------
  newReplySlot() {
    const id = "rs-" + (this._nextSlotId++);
    this.replySlots.set(id, { fulfilled: false, value: null });
    return id;
  }

  fulfillReplySlot(slotId, value) {
    const slot = this.replySlots.get(slotId);
    if (slot && !slot.fulfilled) {
      slot.fulfilled = true;
      slot.value = value;
    }
  }

  // Find any actor with a dispatchable message and process exactly one of
  // them, synchronously (bypassing setTimeout). Returns true if a message
  // was processed, false if nothing was dispatchable.
  _drainOneStep() {
    for (const [, actor] of this.actors) {
      if (actor.processing) continue;
      const idx = actor.mailbox.findIndex(m => actor.methods.has(m.methodName));
      if (idx < 0) continue;
      const msg = actor.mailbox.splice(idx, 1)[0];
      actor.processing = true;
      actor.__currentSlotId = msg.slotId || null;
      try {
        this.invoke(actor, msg.methodName, msg.args, msg.unsafe, msg.senderName);
      } catch (e) {
        this.print(`[ERROR in ${actor.name}.${msg.methodName}] ${e.message}`);
      }
      actor.__currentSlotId = null;
      actor.processing = false;
      return true;
    }
    return false;
  }

  // Drain actor mailboxes until the given slot is fulfilled. Throws if no
  // progress can be made and the slot is still pending.
  drainUntilSlot(slotId) {
    while (!this.replySlots.get(slotId).fulfilled) {
      if (!this._drainOneStep()) {
        throw new Error(`await/now deadlock: slot ${slotId} not fulfilled`);
      }
    }
    return this.replySlots.get(slotId).value;
  }

  // Schedule an actor to process its next dispatchable message
  scheduleActor(actor, delayMs = 0) {
    if (actor.processing || actor.scheduled) return;
    actor.scheduled = true;
    setTimeout(() => {
      actor.scheduled = false;
      this._processNextFor(actor);
    }, delayMs);
  }

  _processNextFor(actor) {
    const idx = actor.mailbox.findIndex(msg => actor.methods.has(msg.methodName));
    if (idx < 0) return;

    const msg = actor.mailbox.splice(idx, 1)[0];
    actor.processing = true;
    try {
      this.invoke(actor, msg.methodName, msg.args, msg.unsafe, msg.senderName);
    } catch (e) {
      this.print(`[ERROR in ${actor.name}.${msg.methodName}] ${e.message}`);
    }
    actor.processing = false;

    const delay = actor.__nextDelay || 0;
    actor.__nextDelay = 0;
    if (actor.mailbox.some(m => actor.methods.has(m.methodName))) {
      this.scheduleActor(actor, delay);
    }
  }

  // Kick off all actors that have pending messages (called after top-level stmts)
  scheduleAllActors() {
    for (const [, actor] of this.actors) {
      if (actor.mailbox.some(m => actor.methods.has(m.methodName))) {
        this.scheduleActor(actor, 0);
      }
    }
  }

  invoke(actor, methodName, args, unsafe = false, senderName = null) {
    const method = actor.methods.get(methodName);
    if (!method) {
      if (unsafe) { this.print(`[unsafe-send ignored] ${actor.className}.${methodName}`); return null; }
      throw new Error(`unknown method at runtime: ${actor.className}.${methodName}`);
    }

    // Env starts with actor instance state (instance variables)
    const env = {
      __currentActor: actor.name,
      sender: senderName,
      ...actor.state,
    };
    method.params.forEach((p, i) => { env[p] = args[i]; });

    let last = null;
    for (const st of method.body.statements) {
      last = this.evalStmt(st, env);
    }

    // Sync mutated instance variables back to actor state
    for (const key of Object.keys(actor.state)) {
      if (key in env) actor.state[key] = env[key];
    }
    return last;
  }

  evalStmt(stmt, env) {
    switch (stmt.type) {
      case "Print": {
        const v = this.evalExpr(stmt.expr, env);
        this.print(v);
        return v;
      }

      case "Reply": {
        const v = this.evalExpr(stmt.expr, env);
        this.replies.push(v);
        // If the current actor was invoked via now/future, fulfill the slot
        // so the awaiting caller can unblock.
        const actorName = env.__currentActor;
        if (actorName) {
          const actor = this.actors.get(actorName);
          if (actor && actor.__currentSlotId) {
            this.fulfillReplySlot(actor.__currentSlotId, v);
          }
        }
        this.print(`[REPLY] value=${v}`);
        return v;
      }

      case "VarDecl": {
        if (stmt.expr.type === "NewExpr") {
          const actorName = stmt.name;
          const className = stmt.expr.className;
          const initArgs = (stmt.expr.args || []).map(a => this.evalExpr(a, env));
          this.createActor(actorName, className, initArgs);
          env[stmt.name] = actorName;
          return actorName;
        }
        const v = this.evalExpr(stmt.expr, env);
        env[stmt.name] = v;
        return v;
      }

      case "Assign": {
        const v = this.evalExpr(stmt.expr, env);
        env[stmt.name] = v;
        // Immediately propagate to actor state if it's an instance variable
        if (env.__currentActor) {
          const actor = this.actors.get(env.__currentActor);
          if (actor && stmt.name in actor.state) actor.state[stmt.name] = v;
        }
        return v;
      }

      case "Send": {
        const senderName = env.__currentActor || null;
        const actorName = this.evalTarget(stmt.target, env);
        const args = stmt.args.map(a => this.evalExpr(a, env));
        this.send(actorName, stmt.method, args, stmt.unsafe, senderName);
        return null;
      }

      case "CallStmt": {
        const args = stmt.args.map(a => this.evalExpr(a, env));
        this._callBuiltin(stmt.name, args, env);
        return null;
      }

      case "If": {
        const c = this.evalExpr(stmt.cond, env);
        if (c) {
          for (const st of stmt.thenBody.statements) this.evalStmt(st, env);
        } else if (stmt.elseBody) {
          for (const st of stmt.elseBody.statements) this.evalStmt(st, env);
        }
        return null;
      }

      case "Select":
        return this.evalSelect(stmt, env);

      default:
        throw new Error("Unsupported statement: " + stmt.type);
    }
  }

  _callBuiltin(name, args, env) {
    const actorName = env.__currentActor || null;
    const actor = actorName ? this.actors.get(actorName) : null;

    // AIOS / protocol builtins: shared dispatch (also reachable from CallExpr)
    const ap = this._dispatchAiosProtocol(name, args, env);
    if (ap.handled) return ap.value;

    switch (name) {
      case "wait": {
        // Delay next message dispatch for this actor
        const ms = Number(args[0]) || 0;
        if (actor) actor.__nextDelay = ms;
        break;
      }
      case "canvas_line":
      case "sdl_line": {
        const [x1, y1, x2, y2] = args;
        if (!this._actorColors.has(actorName)) {
          this._actorColors.set(actorName, ACTOR_COLORS[this._colorIdx++ % ACTOR_COLORS.length]);
        }
        this.scene.set(actorName, { x1, y1, x2, y2, color: this._actorColors.get(actorName) });
        this._redrawCanvas();
        break;
      }
      case "canvas_clear":
      case "sdl_clear":
        // No-op: redrawCanvas clears automatically before drawing
        break;
      case "canvas_present":
      case "sdl_present":
        // No-op for canvas (immediate mode)
        break;
      case "philo_state": {
        // args: (id, state)  state: 0=thinking, 1=hungry, 2=eating
        this.philoStates.set(Number(args[0]), Number(args[1]));
        this._redrawCanvas();
        break;
      }
      case "fork_state": {
        // args: (id, state)  state: 0=free, 1=taken  (legacy — no holder info)
        this.forkStates.set(Number(args[0]), Number(args[1]));
        if (Number(args[1]) === 0) this.forkHolders.delete(Number(args[0]));
        this._redrawCanvas();
        break;
      }
      case "fork_free": {
        // args: (id)  — fork becomes free
        const fid = Number(args[0]);
        this.forkStates.set(fid, 0);
        this.forkHolders.delete(fid);
        this._redrawCanvas();
        break;
      }
      case "fork_held": {
        // args: (id, holderId)  — fork is held by philosopher holderId
        const fid = Number(args[0]);
        const hid = Number(args[1]);
        this.forkStates.set(fid, 1);
        this.forkHolders.set(fid, hid);
        this._redrawCanvas();
        break;
      }
      case "print":
        this.print(args[0]);
        break;

      // ---------------- Bounded buffer visualization -------------
      case "buf_init": {
        const cap = Number(args[0]) || 4;
        this.bufState = {
          cap,
          slots: new Array(cap).fill(null),
          pstate: "idle", cstate: "idle",
          pn: 0, cn: 0,
        };
        this._redrawCanvas();
        break;
      }
      case "buf_set": {
        if (!this.bufState) break;
        const idx = Number(args[0]);
        const val = args[1];
        if (idx >= 0 && idx < this.bufState.slots.length) {
          this.bufState.slots[idx] = val;
          this._redrawCanvas();
        }
        break;
      }
      case "buf_clear": {
        if (!this.bufState) break;
        const idx = Number(args[0]);
        if (idx >= 0 && idx < this.bufState.slots.length) {
          this.bufState.slots[idx] = null;
          this._redrawCanvas();
        }
        break;
      }
      case "buf_pstate": {
        if (!this.bufState) break;
        this.bufState.pstate = String(args[0]);
        this._redrawCanvas();
        break;
      }
      case "buf_cstate": {
        if (!this.bufState) break;
        this.bufState.cstate = String(args[0]);
        this._redrawCanvas();
        break;
      }
      case "buf_pn": {
        if (!this.bufState) break;
        this.bufState.pn = Number(args[0]) || 0;
        this._redrawCanvas();
        break;
      }
      case "buf_cn": {
        if (!this.bufState) break;
        this.bufState.cn = Number(args[0]) || 0;
        this._redrawCanvas();
        break;
      }

      // ---------------- Drone simulator built-ins ----------------
      case "world_setup": {
        const [W, H, commR, viewR] = args;
        this.droneWorld = {
          W: Number(W) || 800,
          H: Number(H) || 600,
          commRange: Number(commR) || 100,
          viewRange: Number(viewR) || 50,
          obstacles: [],
          safeZone: null,
          stats: { arrived: 0, dead: 0, total: 0 },
        };
        if (this.canvas) {
          this.canvas.width  = this.droneWorld.W;
          this.canvas.height = this.droneWorld.H;
        }
        this._redrawCanvas();
        break;
      }
      case "place_obstacle": {
        if (!this.droneWorld) break;
        const [oid, ox, oy, orad] = args;
        this.droneWorld.obstacles.push({
          id: Number(oid), x: Number(ox), y: Number(oy), r: Number(orad),
        });
        this._redrawCanvas();
        break;
      }
      case "place_safe": {
        if (!this.droneWorld) break;
        const [sx, sy, sr] = args;
        this.droneWorld.safeZone = { x: Number(sx), y: Number(sy), r: Number(sr) };
        this._redrawCanvas();
        break;
      }
      case "drone_register": {
        const did = Number(args[0]);
        if (actorName) this.droneActorById.set(did, actorName);
        this.droneKnowledge.set(did, new Set());
        if (this.droneWorld) this.droneWorld.stats.total++;
        break;
      }
      case "drone_pos": {
        const [did, px, py] = args;
        this.dronePositions.set(Number(did), { x: Number(px), y: Number(py) });
        this._redrawCanvas();
        break;
      }
      case "drone_state": {
        const [did, st] = args;
        const prev = this.droneStates.get(Number(did));
        this.droneStates.set(Number(did), Number(st));
        if (this.droneWorld) {
          if (prev !== 1 && Number(st) === 1) this.droneWorld.stats.arrived++;
          if (prev !== 2 && Number(st) === 2) this.droneWorld.stats.dead++;
        }
        this._redrawCanvas();
        break;
      }
      case "drone_scan": {
        if (!this.droneWorld) break;
        const [did, px, py] = args;
        const vR = this.droneWorld.viewRange;
        const dronePos = { x: Number(px), y: Number(py) };
        const known = this.droneKnowledge.get(Number(did)) || new Set();
        for (const ob of this.droneWorld.obstacles) {
          if (known.has(ob.id)) continue;
          const d = Math.hypot(ob.x - dronePos.x, ob.y - dronePos.y) - ob.r;
          if (d <= vR) {
            const aName = this.droneActorById.get(Number(did));
            if (aName) this.send(aName, "learn_obstacle", [ob.id, ob.x, ob.y, ob.r], true, null);
          }
        }
        break;
      }
      case "drone_broadcast": {
        if (!this.droneWorld) break;
        const [srcId, obsId, ox, oy, orad] = args;
        const srcPos = this.dronePositions.get(Number(srcId));
        if (!srcPos) break;
        const cR = this.droneWorld.commRange;
        for (const [otherId, pos] of this.dronePositions) {
          if (otherId === Number(srcId)) continue;
          const d = Math.hypot(pos.x - srcPos.x, pos.y - srcPos.y);
          if (d > cR) continue;
          const known = this.droneKnowledge.get(otherId);
          if (known && known.has(Number(obsId))) continue;
          const aName = this.droneActorById.get(otherId);
          if (aName) this.send(aName, "learn_obstacle", [Number(obsId), ox, oy, orad], true, null);
        }
        break;
      }
      case "drone_remember": {
        const [did, obsId] = args;
        const k = this.droneKnowledge.get(Number(did));
        if (k) k.add(Number(obsId));
        break;
      }

      default:
        this.print(`[call] ${name}(${args.join(", ")})`);
    }
  }

  _redrawCanvas() {
    if (!this.canvas) return;
    const ctx = this.canvas.getContext("2d");
    const W = this.canvas.width, H = this.canvas.height;

    // Clear background (wireframe dark blue)
    ctx.fillStyle = "#0a0a1a";
    ctx.fillRect(0, 0, W, H);

    // Rotating line segments (Rotate4Lines etc.)
    ctx.lineWidth = 2;
    for (const [, seg] of this.scene) {
      ctx.strokeStyle = seg.color;
      ctx.beginPath();
      ctx.moveTo(seg.x1, seg.y1);
      ctx.lineTo(seg.x2, seg.y2);
      ctx.stroke();
    }

    // Dining Philosophers wireframe
    if (this.philoStates.size > 0 || this.forkStates.size > 0) {
      this._drawPhilosophers(ctx, W, H);
    }

    // Drone return-route simulator
    if (this.droneWorld) {
      this._drawDroneWorld(ctx, W, H);
    }

    // Bounded buffer
    if (this.bufState) {
      this._drawBufferState(ctx, W, H);
    }
  }

  _drawBufferState(ctx, W, H) {
    const s = this.bufState;
    const cap = s.cap;

    // Layout: producer box (left) — buffer slots (middle) — consumer box (right)
    const PROD_X = 60;
    const CONS_X = W - 60;
    const ROW_Y  = Math.floor(H / 2);

    const slotW = Math.max(18, Math.min(40, Math.floor((W - 240) / cap) - 2));
    const slotH = 36;
    const gap   = 2;
    const totalW = cap * slotW + (cap - 1) * gap;
    const bufLeft = Math.floor(W / 2 - totalW / 2);
    const slotCx = (i) => bufLeft + i * (slotW + gap) + slotW / 2;

    // Background row
    ctx.fillStyle = "#10101e";
    ctx.fillRect(bufLeft - 10, ROW_Y - slotH/2 - 6, totalW + 20, slotH + 12);

    // Producer box
    {
      const blocked = s.pstate === "blocked";
      ctx.fillStyle   = blocked ? "#3a2410" : "#142848";
      ctx.strokeStyle = blocked ? "#ff9955" : "#66ccff";
      ctx.lineWidth = 2;
      ctx.fillRect(PROD_X - 40, ROW_Y - 28, 80, 56);
      ctx.strokeRect(PROD_X - 40, ROW_Y - 28, 80, 56);
      ctx.fillStyle = "#fff";
      ctx.font = "bold 12px monospace";
      ctx.textAlign = "center";
      ctx.fillText("Producer", PROD_X, ROW_Y - 8);
      ctx.fillStyle = blocked ? "#ff9955" : "#aef";
      ctx.font = "10px monospace";
      ctx.fillText(blocked ? "BLOCKED" : (s.pstate || "idle"), PROD_X, ROW_Y + 8);
      ctx.fillStyle = "#88c0ff";
      ctx.fillText("sent=" + s.pn, PROD_X, ROW_Y + 22);
    }

    // Consumer box
    {
      const blocked = s.cstate === "blocked";
      ctx.fillStyle   = blocked ? "#3a2410" : "#3a2a14";
      ctx.strokeStyle = blocked ? "#ff9955" : "#ffcc66";
      ctx.lineWidth = 2;
      ctx.fillRect(CONS_X - 40, ROW_Y - 28, 80, 56);
      ctx.strokeRect(CONS_X - 40, ROW_Y - 28, 80, 56);
      ctx.fillStyle = "#fff";
      ctx.font = "bold 12px monospace";
      ctx.textAlign = "center";
      ctx.fillText("Consumer", CONS_X, ROW_Y - 8);
      ctx.fillStyle = blocked ? "#ff9955" : "#fe9";
      ctx.font = "10px monospace";
      ctx.fillText(blocked ? "BLOCKED" : (s.cstate || "idle"), CONS_X, ROW_Y + 8);
      ctx.fillStyle = "#ffd088";
      ctx.fillText("taken=" + s.cn, CONS_X, ROW_Y + 22);
    }

    // Arrows from producer to buffer & buffer to consumer
    ctx.strokeStyle = "#445";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(PROD_X + 40, ROW_Y);
    ctx.lineTo(bufLeft - 4, ROW_Y);
    ctx.moveTo(bufLeft + totalW + 4, ROW_Y);
    ctx.lineTo(CONS_X - 40, ROW_Y);
    ctx.stroke();

    // Buffer slots
    let filled = 0;
    for (let i = 0; i < cap; i++) {
      const x = bufLeft + i * (slotW + gap);
      const y = ROW_Y - slotH / 2;
      const v = s.slots[i];
      const has = v !== null && v !== undefined;
      if (has) filled++;
      ctx.fillStyle   = has ? "#123a20" : "#101022";
      ctx.fillRect(x, y, slotW, slotH);
      ctx.strokeStyle = has ? "#55ff55" : "#445";
      ctx.lineWidth = 1.5;
      ctx.strokeRect(x, y, slotW, slotH);
      if (has) {
        ctx.fillStyle = "#afe";
        ctx.textAlign = "center";
        const lbl = String(v);
        ctx.font = lbl.length <= 2 ? "bold 13px monospace"
                 : lbl.length <= 3 ? "bold 10px monospace"
                 :                   "bold 8px monospace";
        ctx.fillText(lbl, x + slotW/2, ROW_Y + 5);
      }
      // index labels every few slots
      if (cap <= 8 || i % 5 === 0 || i === cap - 1) {
        ctx.fillStyle = "#667";
        ctx.font = "9px monospace";
        ctx.fillText("s" + i, x + slotW/2, y + slotH + 10);
      }
    }

    // count display
    ctx.fillStyle = "#778";
    ctx.font = "11px monospace";
    ctx.textAlign = "center";
    ctx.fillText(`count = ${filled} / ${cap}`,
                 bufLeft + totalW / 2, ROW_Y - slotH/2 - 14);
  }

  _drawDroneWorld(ctx, W, H) {
    const world = this.droneWorld;

    // Safe zone (destination) — green region
    if (world.safeZone) {
      const sz = world.safeZone;
      ctx.fillStyle   = "rgba(60, 220, 120, 0.25)";
      ctx.strokeStyle = "#3ddc78";
      ctx.lineWidth   = 2;
      ctx.beginPath();
      ctx.arc(sz.x, sz.y, sz.r, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = "#3ddc78";
      ctx.font = "11px monospace";
      ctx.textAlign = "center";
      ctx.fillText("SAFE", sz.x, sz.y + 4);
    }

    // Obstacles (impassable disaster zones) — purple
    for (const ob of world.obstacles) {
      ctx.fillStyle   = "rgba(160, 60, 200, 0.28)";
      ctx.strokeStyle = "#c060e0";
      ctx.lineWidth   = 2;
      ctx.beginPath();
      ctx.arc(ob.x, ob.y, ob.r, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = "#d890f0";
      ctx.font = "11px monospace";
      ctx.textAlign = "center";
      ctx.fillText("X" + ob.id, ob.x, ob.y + 4);
    }

    // MANET links — thin lines between drones within comm range
    const positions = Array.from(this.dronePositions.entries());
    const cR = world.commRange;
    ctx.strokeStyle = "rgba(120, 160, 255, 0.28)";
    ctx.lineWidth   = 1;
    for (let i = 0; i < positions.length; i++) {
      const [idA, pa] = positions[i];
      const sA = this.droneStates.get(idA) || 0;
      if (sA === 2) continue;
      for (let j = i + 1; j < positions.length; j++) {
        const [idB, pb] = positions[j];
        const sB = this.droneStates.get(idB) || 0;
        if (sB === 2) continue;
        const d = Math.hypot(pa.x - pb.x, pa.y - pb.y);
        if (d <= cR) {
          ctx.beginPath();
          ctx.moveTo(pa.x, pa.y);
          ctx.lineTo(pb.x, pb.y);
          ctx.stroke();
        }
      }
    }

    // Drones — red dots (arrived=green, dead=gray); informed drones get a yellow halo
    for (const [id, pos] of this.dronePositions) {
      const st    = this.droneStates.get(id) || 0;
      const known = this.droneKnowledge.get(id);
      if (known && known.size > 0 && st !== 2) {
        ctx.strokeStyle = "rgba(255, 220, 80, 0.7)";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(pos.x, pos.y, 7, 0, Math.PI * 2);
        ctx.stroke();
      }
      let fill = "#ff4a5c";
      if (st === 1) fill = "#3ddc78";
      else if (st === 2) fill = "#666";
      ctx.fillStyle = fill;
      ctx.beginPath();
      ctx.arc(pos.x, pos.y, 4, 0, Math.PI * 2);
      ctx.fill();
    }

    // Stats HUD
    const s = world.stats;
    ctx.fillStyle = "#aac";
    ctx.font = "12px monospace";
    ctx.textAlign = "left";
    ctx.fillText(`drones:${s.total}  arrived:${s.arrived}  dead:${s.dead}`, 8, 16);
    ctx.fillText(`comm=${world.commRange}  view=${world.viewRange}`, 8, 32);
  }

  _drawPhilosophers(ctx, W, H) {
    const N = 5;
    const cx = W / 2, cy = H / 2;
    const R  = Math.min(W, H) * 0.32;       // philosopher ring radius

    const PHILO_COLORS = ["#ff5566", "#ffa833", "#3ddc6e", "#3aa8ff", "#c765ff"];
    const STATE_NAME   = ["THINK", "HUNGRY", "EAT"];
    const STATE_INNER  = ["#334",  "#ffcc40", "#40e070"];

    // Pentagon vertices — philosopher positions
    const philoPos = [];
    for (let i = 0; i < N; i++) {
      const theta = -Math.PI / 2 + (i * 2 * Math.PI / N);
      philoPos.push({
        x: cx + R * Math.cos(theta),
        y: cy + R * Math.sin(theta),
        theta,
      });
    }

    // Fork rest positions — midpoints of pentagon EDGES. This places each
    // fork geometrically between the two philosophers who share it (exactly
    // where you'd expect a fork on a round table). Fork i is between phil i
    // and phil (i+1)%N.
    const forkPos = [];
    for (let i = 0; i < N; i++) {
      const a = philoPos[i], b = philoPos[(i + 1) % N];
      const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
      // Tangent direction (along the edge) — used for the FREE orientation.
      const ex = b.x - a.x, ey = b.y - a.y;
      const elen = Math.hypot(ex, ey) || 1;
      forkPos.push({
        x: mx, y: my,
        tx: ex / elen, ty: ey / elen,        // unit tangent along the edge
      });
    }

    // Table outline — pentagon edges in a dim hue
    ctx.strokeStyle = "#262640";
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let i = 0; i < N; i++) {
      const a = philoPos[i], b = philoPos[(i + 1) % N];
      if (i === 0) ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
    }
    ctx.closePath();
    ctx.stroke();

    // Forks ---------------------------------------------------------------
    //   FREE : short gray line at the edge-midpoint, oriented ALONG the edge
    //   HELD : fork translates 50 % toward the holder, adopts the holder's
    //          colour, a perpendicular bar shows the fork head, and an arrow
    //          with an arrowhead points at the holder's circle.
    for (let i = 0; i < N; i++) {
      const fp = forkPos[i];
      const restX = fp.x, restY = fp.y;
      const state    = this.forkStates.get(i) || 0;
      const holderId = this.forkHolders.get(i);

      if (state === 0 || holderId === undefined) {
        // FREE — lay the fork along the edge (tangent direction)
        const tx = fp.tx, ty = fp.ty;
        ctx.strokeStyle = "#7a7aa0";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(restX - tx * 13, restY - ty * 13);
        ctx.lineTo(restX + tx * 13, restY + ty * 13);
        ctx.stroke();
        // Label — slightly toward centre
        const cdx = cx - restX, cdy = cy - restY;
        const clen = Math.hypot(cdx, cdy) || 1;
        const lx = restX + (cdx / clen) * 14;
        const ly = restY + (cdy / clen) * 14;
        ctx.fillStyle = "#9a9abc";
        ctx.font = "10px monospace";
        ctx.textAlign = "center";
        ctx.fillText("F" + i, lx, ly);
      } else {
        // HELD
        const holder = philoPos[holderId];
        if (!holder) continue;
        const dx = holder.x - restX;
        const dy = holder.y - restY;
        const dist = Math.hypot(dx, dy) || 1;
        const ux = dx / dist, uy = dy / dist;

        // Fork bar at 30 % along rest→holder (close to rest) so the arrow
        // shaft has plenty of room. Arrow head sits a fixed pixel margin
        // OUTSIDE the philosopher's circle (radius 22) so the arrowhead is
        // clearly visible and never inside the circle.
        const PHILO_RADIUS = 22;
        const ARROW_OUTSIDE_GAP = 8;       // gap between arrow tip and circle edge
        const endPxFromHolder = PHILO_RADIUS + ARROW_OUTSIDE_GAP;  // 30
        const forkFrac      = 0.30;        // bar near rest, leaves room for a long shaft
        const startFrac     = forkFrac + 0.05;  // shaft starts just past the bar
        let   endFrac       = 1 - endPxFromHolder / dist;
        // Guarantee a visibly long shaft. On small canvases the geometry
        // gets squeezed; we keep the shaft at least 20 % of dist long even
        // if that means the arrowhead lands just inside the circle.
        const MIN_SHAFT_FRAC = 0.20;
        if (endFrac < startFrac + MIN_SHAFT_FRAC) endFrac = startFrac + MIN_SHAFT_FRAC;

        const forkX = restX + ux * dist * forkFrac;
        const forkY = restY + uy * dist * forkFrac;
        const color = PHILO_COLORS[holderId];

        // Fork bar — perpendicular to the rest→holder line.
        // Bar half-length scales with dist so it stays proportional.
        const barHalf = Math.max(6, Math.min(12, dist * 0.15));
        const px = -uy, py = ux;
        ctx.strokeStyle = color;
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.moveTo(forkX - px * barHalf, forkY - py * barHalf);
        ctx.lineTo(forkX + px * barHalf, forkY + py * barHalf);
        ctx.stroke();

        // Arrow shaft — from past the fork bar toward the holder.
        const shaftStartX = restX + ux * dist * startFrac;
        const shaftStartY = restY + uy * dist * startFrac;
        const shaftEndX   = restX + ux * dist * endFrac;
        const shaftEndY   = restY + uy * dist * endFrac;
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

        // Fork label — at rest position, so you can still see where the
        // fork is "supposed to live" when free.
        ctx.fillStyle = color;
        ctx.font = "10px monospace";
        ctx.textAlign = "center";
        const cdx = cx - restX, cdy = cy - restY;
        const clen = Math.hypot(cdx, cdy) || 1;
        ctx.fillText("F" + i,
                     restX + (cdx / clen) * 14,
                     restY + (cdy / clen) * 14);
      }
    }

    // Philosophers --------------------------------------------------------
    ctx.textAlign = "center";
    for (let i = 0; i < N; i++) {
      const p = philoPos[i];
      const state = this.philoStates.get(i) ?? 0;
      const base  = PHILO_COLORS[i];

      // Outer circle — philosopher's base colour, thickness by state
      ctx.strokeStyle = base;
      ctx.lineWidth = state === 2 ? 3 : (state === 1 ? 2 : 1);
      ctx.beginPath();
      ctx.arc(p.x, p.y, 22, 0, Math.PI * 2);
      ctx.stroke();

      // Inner state dot
      ctx.fillStyle = STATE_INNER[state];
      ctx.beginPath();
      ctx.arc(p.x, p.y, state === 2 ? 10 : 6, 0, Math.PI * 2);
      ctx.fill();

      // Labels
      ctx.fillStyle = base;
      ctx.font = "bold 13px monospace";
      ctx.fillText("P" + i, p.x, p.y + 4);
      ctx.font = "9px monospace";
      ctx.fillText(STATE_NAME[state], p.x, p.y + 36);
    }
  }

  // Shared AIOS/Protocol dispatch used by both evalExpr CallExpr and
  // _callBuiltin (CallStmt). args are pre-evaluated. Returns
  // { handled: true, value } when matched, or { handled: false }.
  _dispatchAiosProtocol(name, args, env) {
    const senderName = (env && env.__currentActor) || null;
    switch (name) {
      case "aios_register_service":
        this.aiosRegisterService(args[0], args[1]);
        return { handled: true, value: null };
      case "aios_emit":
        this.aiosEmit(args[0]);
        return { handled: true, value: null };
      case "aios_services":
        return { handled: true, value: this.aiosServicesString() };
      case "aios_events":
        return { handled: true, value: this.aiosEventsString() };
      case "aios_now": {
        const alias = String(args[0]);
        const method = String(args[1]);
        const rest = args.slice(2);
        const target = this.aiosResolve(alias);
        const slotId = this.newReplySlot();
        this.send(target, method, rest, false, senderName, slotId);
        const reply = this.drainUntilSlot(slotId);
        this.protocolObserveAll(alias, method);
        return { handled: true, value: reply };
      }
      case "aios_future": {
        const alias = String(args[0]);
        const method = String(args[1]);
        const rest = args.slice(2);
        const target = this.aiosResolve(alias);
        const slotId = this.newReplySlot();
        this.send(target, method, rest, false, senderName, slotId);
        return { handled: true, value: { __future: true, slotId,
                 _aios_meta: { alias, method, args: rest } } };
      }
      case "protocol_define":
        this.protocolDefine(args[0], args[1]);
        return { handled: true, value: null };
      case "protocol_start":
        return { handled: true, value: this.protocolStart(String(args[0])) };
      case "protocol_state":
        return { handled: true, value: this.protocolStateString(String(args[0])) };
      case "protocol_end":
        this.protocolEnd(String(args[0]));
        return { handled: true, value: null };
      case "protocol_events":
        return { handled: true, value: this.protocolEventsString() };
    }
    return { handled: false };
  }

  // ---- AIOS coordination helpers ------------------------------------
  aiosResolve(alias) {
    return this._aiosServices.get(alias) || alias;
  }
  aiosEmit(msg) { this._aiosEvents.push("[EMIT] " + String(msg)); }
  aiosRegisterService(alias, actorName) {
    this._aiosServices.set(String(alias), String(actorName));
    this._aiosEvents.push(`[REGISTER] ${alias} -> ${actorName}`);
  }
  aiosServicesString() {
    return "[" + Array.from(this._aiosServices.entries())
      .map(([a, n]) => `${a}=${n}`).join(", ") + "]";
  }
  aiosEventsString() { return this._aiosEvents.join("\n"); }

  protocolDefine(name, spec) {
    const steps = String(spec).split("->").map(s => s.trim()).filter(Boolean);
    this._protoDefs.set(String(name), steps);
    this._protoEvents.push(`[PROTO_DEF] ${name} = [${steps.join(", ")}]`);
  }
  protocolStart(name) {
    if (!this._protoDefs.has(name)) throw new Error("protocol_start: unknown " + name);
    this._protoSeq += 1;
    const sid = `proto-${this._protoSeq}-${Date.now()}`;
    this._protoActive.set(sid, { name, idx: 0, ended: false });
    this._protoEvents.push(`[PROTO_START] sid=${sid} proto=${name}`);
    return sid;
  }
  protocolObserveAll(actorAlias, method) {
    const step = `${actorAlias}.${method}`;
    for (const [, st] of this._protoActive) {
      if (st.ended) continue;
      const defn = this._protoDefs.get(st.name) || [];
      if (st.idx < defn.length && defn[st.idx] === step) st.idx += 1;
    }
  }
  protocolStateString(sid) {
    const st = this._protoActive.get(sid);
    if (!st) return `[PROTO_STATE] sid=${sid} (unknown)`;
    const defn = this._protoDefs.get(st.name) || [];
    const next = st.idx < defn.length ? defn[st.idx] : "(done)";
    const status = st.ended ? "ended" : "running";
    return `[PROTO_STATE] sid=${sid} proto=${st.name} progress=${st.idx}/${defn.length} next=${next} status=${status}`;
  }
  protocolEnd(sid) {
    const st = this._protoActive.get(sid);
    if (st) st.ended = true;
    this._protoEvents.push(`[PROTO_END] sid=${sid}`);
  }
  protocolEventsString() { return this._protoEvents.join("\n"); }

  // ---- AI integration -----------------------------------------------
  // Default: a synchronous mock provider so the cooperative sample runs
  // offline in any environment. To use a real provider, override this
  // method on a Runtime instance (the Node runner in run_cooperative.mjs
  // does this with execSync + curl).
  _aiCall(prompt, system = null) {
    const sysTag = system ? ` sys=(${String(system).slice(0, 12)}...)` : "";
    const head = String(prompt ?? "").slice(0, 60);
    return `[mock] reply${sysTag} for: ${head}`;
  }

  evalTarget(target, env) {
    if (typeof target === "string") {
      if (target === "self") return env.__currentActor || "self";
      if (target in env) return env[target];
      if (this.actors.has(target)) return target;
      return target;
    }
    throw new Error("Unsupported send target: " + JSON.stringify(target));
  }

  evalSelect(stmt, env) {
    const actorName = env.__currentActor;
    if (!actorName) throw new Error("select used outside actor method");
    const actor = this.actors.get(actorName);
    if (!actor) throw new Error("current actor not found: " + actorName);

    let matchedIndex = -1, matchedCase = null, matchedMsg = null;
    for (let i = 0; i < actor.mailbox.length; i++) {
      const msg = actor.mailbox[i];
      for (const c of stmt.cases) {
        if (msg.methodName === c.method) {
          matchedIndex = i; matchedCase = c; matchedMsg = msg;
          break;
        }
      }
      if (matchedCase) break;
    }

    if (matchedCase) {
      actor.mailbox.splice(matchedIndex, 1);
      const localEnv = { ...env };
      matchedCase.params.forEach((p, i) => { localEnv[p] = matchedMsg.args[i]; });
      let last = null;
      for (const st of matchedCase.body.statements) last = this.evalStmt(st, localEnv);
      return last;
    }

    if (stmt.timeoutBody) {
      this.print(`[timeout] ${stmt.timeoutMs}ms`);
      let last = null;
      for (const st of stmt.timeoutBody.statements) last = this.evalStmt(st, env);
      return last;
    }
    return null;
  }

  evalExpr(expr, env) {
    switch (expr.type) {
      case "IntLit":    return expr.value;
      case "FloatLit":  return expr.value;
      case "StringLit": return expr.value;

      case "Var":
        if (expr.name in env) return env[expr.name];
        if (this.actors.has(expr.name)) return expr.name;
        throw new Error("Unknown var: " + expr.name);

      case "Binop": {
        const l = this.evalExpr(expr.left, env);
        const r = this.evalExpr(expr.right, env);
        switch (expr.op) {
          case "+":  return l + r;
          case "-":  return l - r;
          case "*":  return l * r;
          case "/":  return l / r;
          case "==": return l === r ? 1 : 0;
          case "!=": return l !== r ? 1 : 0;
          case "<":  return l <  r ? 1 : 0;
          case ">":  return l >  r ? 1 : 0;
          case "<=": return l <= r ? 1 : 0;
          case ">=": return l >= r ? 1 : 0;
        }
        throw new Error("Unsupported op: " + expr.op);
      }

      case "CallExpr": {
        const args = expr.args.map(a => this.evalExpr(a, env));
        switch (expr.name) {
          case "cos":   return Math.cos(args[0]);
          case "sin":   return Math.sin(args[0]);
          case "sqrt":  return Math.sqrt(args[0]);
          case "abs":   return Math.abs(args[0]);
          case "floor": return Math.floor(args[0]);
          case "rand":  return Math.floor(Math.random() * (Number(args[0]) || 1));
          case "randf": return Math.random() * (Number(args[0]) || 1);
          case "ai_call":             return this._aiCall(args[0]);
          case "ai_call_with_system": return this._aiCall(args[1], args[0]);
          case "prod_speed":          return this._prodSpeed;
          case "cons_speed":          return this._consSpeed;
          default: {
            // AIOS / protocol builtins (shared with CallStmt)
            const ap = this._dispatchAiosProtocol(expr.name, args, env);
            if (ap.handled) return ap.value;
            throw new Error("Unknown function: " + expr.name);
          }
        }
      }

      case "Now": {
        const senderName = env.__currentActor || null;
        const target = this.evalTarget(expr.target, env);
        const args = expr.args.map(a => this.evalExpr(a, env));
        const slotId = this.newReplySlot();
        this.send(target, expr.method, args, false, senderName, slotId);
        return this.drainUntilSlot(slotId);
      }

      case "Future": {
        const senderName = env.__currentActor || null;
        const target = this.evalTarget(expr.target, env);
        const args = expr.args.map(a => this.evalExpr(a, env));
        const slotId = this.newReplySlot();
        this.send(target, expr.method, args, false, senderName, slotId);
        return { __future: true, slotId };
      }

      case "Await": {
        const fut = this.evalExpr(expr.expr, env);
        if (fut && typeof fut === "object" && fut.__future) {
          const value = this.drainUntilSlot(fut.slotId);
          if (fut._aios_meta) {
            this.protocolObserveAll(fut._aios_meta.alias, fut._aios_meta.method);
          }
          return value;
        }
        // await on a plain value is a no-op (parity with Python)
        return fut;
      }

      case "NewExpr": {
        const name = expr.className.toLowerCase() + this.nextId++;
        const initArgs = (expr.args || []).map(a => this.evalExpr(a, env));
        this.createActor(name, expr.className, initArgs);
        return name;
      }

      default:
        throw new Error("Unsupported expr: " + expr.type);
    }
  }
}
