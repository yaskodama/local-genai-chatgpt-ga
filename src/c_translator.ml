(* c_translator.ml — AIPL から C への簡易トランスレータ *)

open Ast

type ctx = {
  cname  : string;
  fields : string list;
  params : string list;
  mutable locals : string list;
}

let buf = Buffer.create 8192
let emit s = Buffer.add_string buf s
let emitf fmt = Printf.ksprintf emit fmt

let classes_of p = List.filter_map (function Class c -> Some c | _ -> None) p
let globals_of p = List.filter_map (function Global s -> Some s | _ -> None) p

let fields_of (c : class_decl) =
  List.filter_map
    (fun s -> match s.sdesc with VarDecl (n, _) -> Some n | _ -> None)
    c.fields

let global_names (gs : stmt list) : string list =
  List.filter_map
    (fun s -> match s.sdesc with VarDecl (n, _) -> Some n | _ -> None)
    gs

(* libc/系統名との衝突を避けるためのマングリング *)
let mangle = function
  | "cos"  -> "b_cos"
  | "sin"  -> "b_sin"
  | "tan"  -> "b_tan"
  | "sqrt" -> "b_sqrt"
  | "abs"  -> "b_abs"
  | f      -> f

(* ---------- AST 走査：外部関数の名前を収集 ---------- *)
let rec walk_expr (acc : string list) (e : expr) : string list =
  let acc =
    match e.desc with
    | Call (f, _) when f <> "print" ->
        let m = mangle f in if List.mem m acc then acc else m :: acc
    | _ -> acc
  in
  match e.desc with
  | Binop (_, a, b)   -> walk_expr (walk_expr acc a) b
  | Call (_, args)    -> List.fold_left walk_expr acc args
  | New (_, args)     -> List.fold_left walk_expr acc args
  | Expr e            -> walk_expr acc e
  | Array (es, _)     -> List.fold_left walk_expr acc es
  | _                 -> acc

let rec walk_stmt (acc : string list) (s : stmt) : string list =
  match s.sdesc with
  | Assign (_, e)             -> walk_expr acc e
  | VarDecl (_, e)            -> walk_expr acc e
  | CallStmt (f, args) ->
      let acc =
        if f = "print" then acc
        else
          let m = mangle f in
          if List.mem m acc then acc else m :: acc
      in
      List.fold_left walk_expr acc args
  | Send (_, _, args) | UnsafeSend (_, _, args) ->
      List.fold_left walk_expr acc args
  | Become (_, args)          -> List.fold_left walk_expr acc args
  | Seq ss                    -> List.fold_left walk_stmt acc ss
  | If (e, s1, s2)            -> walk_stmt (walk_stmt (walk_expr acc e) s1) s2
  | While (e, body)           -> walk_stmt (walk_expr acc e) body
  | Select (cases, (_, tb)) ->
      let acc = List.fold_left (fun a (c : select_case) -> walk_stmt a c.body) acc cases in
      (match tb with Some t -> walk_stmt acc t | None -> acc)

let collect_externs (p : program) : string list =
  let acc = List.fold_left
      (fun acc d ->
        match d with
        | Class c ->
            let acc = List.fold_left walk_stmt acc c.fields in
            List.fold_left (fun a (m : method_decl) -> walk_stmt a m.body)
              acc c.methods
        | Global s -> walk_stmt acc s)
      [] p
  in
  List.rev acc

(* ---------- 式 ---------- *)
let rec gen_expr ~ctx (e : expr) : string =
  match e.desc with
  | Int n      -> Printf.sprintf "mk_int(%dL)" n
  | Float f    -> Printf.sprintf "mk_float(%f)" f
  | String s   -> Printf.sprintf "mk_str(\"%s\")" (String.escaped s)
  | Var x ->
      if x = "self"   then "mk_obj(self_id)"
      else if x = "sender" then "mk_obj(sender_id)"
      else if List.mem x ctx.params then Printf.sprintf "p_%s" x
      else if List.mem x ctx.locals then Printf.sprintf "l_%s" x
      else if List.mem x ctx.fields then
        Printf.sprintf "objects[self_id].fields[F_%s_%s]" ctx.cname x
      else
        Printf.sprintf "mk_obj(g_%s)" x
  | Binop (op, a, b) ->
      Printf.sprintf "v_binop(\"%s\", %s, %s)" op (gen_expr ~ctx a) (gen_expr ~ctx b)
  | Call ("print", [arg]) ->
      Printf.sprintf "(v_print(%s), mk_int(0L))" (gen_expr ~ctx arg)
  | Call (f, args) ->
      let n = List.length args in
      let argstr =
        if n = 0 then "NULL"
        else
          "(value_t[]){"
          ^ String.concat ", " (List.map (gen_expr ~ctx) args)
          ^ "}"
      in
      Printf.sprintf "%s(%d, %s)" (mangle f) n argstr
  | New (cls, args) ->
      let n = List.length args in
      let argstr =
        if n = 0 then "NULL"
        else
          "(value_t[]){"
          ^ String.concat ", " (List.map (gen_expr ~ctx) args)
          ^ "}"
      in
      Printf.sprintf "mk_obj(create_obj(CLASS_%s, %d, %s))" cls n argstr
  | Expr e   -> gen_expr ~ctx e
  | Array _  -> "mk_int(0L)"

(* send target -> 受信 object id を表すC式 *)
let target_id ~ctx tgt =
  match tgt with
  | RemoteTarget _ -> "-1"
  | LocalTarget t ->
      if t = "self"   then "self_id"
      else if t = "sender" then "sender_id"
      else if List.mem t ctx.params then Printf.sprintf "p_%s.obj_id" t
      else if List.mem t ctx.locals then Printf.sprintf "l_%s.obj_id" t
      else if List.mem t ctx.fields then
        Printf.sprintf "objects[self_id].fields[F_%s_%s].obj_id" ctx.cname t
      else
        Printf.sprintf "g_%s" t

(* ---------- 文 ---------- *)
let rec gen_stmt ~ctx ?(indent = 2) (s : stmt) =
  let ind = String.make indent ' ' in
  match s.sdesc with
  | Seq ss -> List.iter (gen_stmt ~ctx ~indent) ss
  | VarDecl (x, e) ->
      let e_c = gen_expr ~ctx e in
      ctx.locals <- x :: ctx.locals;
      emitf "%svalue_t l_%s = %s;\n" ind x e_c
  | Assign (x, e) ->
      let e_c = gen_expr ~ctx e in
      if List.mem x ctx.fields then
        emitf "%sobjects[self_id].fields[F_%s_%s] = %s;\n" ind ctx.cname x e_c
      else if List.mem x ctx.params then
        emitf "%sp_%s = %s;\n" ind x e_c
      else if List.mem x ctx.locals then
        emitf "%sl_%s = %s;\n" ind x e_c
      else
        emitf "%s/* unknown var %s */\n" ind x
  | CallStmt ("print", [arg]) ->
      emitf "%sv_print(%s);\n" ind (gen_expr ~ctx arg)
  | CallStmt (f, args) ->
      let n = List.length args in
      let argstr =
        if n = 0 then "NULL"
        else
          "(value_t[]){"
          ^ String.concat ", " (List.map (gen_expr ~ctx) args)
          ^ "}"
      in
      emitf "%s%s(%d, %s);\n" ind (mangle f) n argstr
  | Send (tgt, meth, args) | UnsafeSend (tgt, meth, args) ->
      let rid = target_id ~ctx tgt in
      let n   = List.length args in
      let argstr =
        if n = 0 then "NULL"
        else
          "(value_t[]){"
          ^ String.concat ", " (List.map (gen_expr ~ctx) args)
          ^ "}"
      in
      emitf "%senqueue(self_id, %s, \"%s\", %d, %s);\n" ind rid meth n argstr
  | If (e, s1, s2) ->
      emitf "%sif (truthy(%s)) {\n" ind (gen_expr ~ctx e);
      gen_stmt ~ctx ~indent:(indent + 2) s1;
      emitf "%s} else {\n" ind;
      gen_stmt ~ctx ~indent:(indent + 2) s2;
      emitf "%s}\n" ind
  | While (e, body) ->
      emitf "%swhile (truthy(%s)) {\n" ind (gen_expr ~ctx e);
      gen_stmt ~ctx ~indent:(indent + 2) body;
      emitf "%s}\n" ind
  | Become _ -> emitf "%s/* become unsupported */\n" ind
  | Select _ -> emitf "%s/* select unsupported */\n" ind

(* ---------- メソッド ---------- *)
let gen_method ~cname ~fields (md : method_decl) =
  let ctx = { cname; fields; params = md.params; locals = [] } in
  emitf "static void %s_%s(int self_id, int sender_id, value_t* args, int n_args) {\n"
    cname md.mname;
  emit "  (void)args; (void)n_args; (void)sender_id;\n";
  List.iteri
    (fun i p ->
      emitf "  value_t p_%s = (n_args > %d) ? args[%d] : mk_int(0L);\n" p i i)
    md.params;
  gen_stmt ~ctx md.body;
  emit "}\n\n"

let gen_class (c : class_decl) =
  let fields = fields_of c in
  if fields <> [] then begin
    emit "enum { ";
    List.iter (fun f -> emitf "F_%s_%s, " c.cname f) fields;
    emitf "F_%s__N };\n\n" c.cname
  end;
  (* フィールド初期化関数 *)
  emitf "static void init_fields_%s(int self_id) {\n" c.cname;
  emit "  (void)self_id;\n";
  let init_ctx = { cname = c.cname; fields; params = []; locals = [] } in
  List.iter (fun s ->
    match s.sdesc with
    | VarDecl (name, e) ->
        emitf "  objects[self_id].fields[F_%s_%s] = %s;\n"
          c.cname name (gen_expr ~ctx:init_ctx e)
    | _ -> ()
  ) c.fields;
  emit "}\n\n";
  List.iter (fun md -> gen_method ~cname:c.cname ~fields md) c.methods;
  emitf "static void dispatch_%s(int self_id, int sender_id, const char* method, value_t* args, int n_args) {\n"
    c.cname;
  List.iter
    (fun md ->
      emitf
        "  if (strcmp(method, \"%s\") == 0) { %s_%s(self_id, sender_id, args, n_args); return; }\n"
        md.mname c.cname md.mname)
    c.methods;
  (* init が定義されていなければ、自動 init は無視 *)
  let has_init = List.exists (fun md -> md.mname = "init") c.methods in
  if not has_init then
    emit "  if (strcmp(method, \"init\") == 0) return; /* default no-op init */\n";
  emitf "  fprintf(stderr, \"unknown method %%s on %s\\n\", method);\n" c.cname;
  emit "}\n\n"

(* ---------- ランタイム (pthread 版) ---------- *)
let runtime_prelude = {|#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <time.h>
#include <pthread.h>

#define MAX_MAILBOX 256
#define MAX_OBJECTS 64
#define MAX_FIELDS  16
#define MAX_ARGS    8

/* メッセージ処理上限と静止検出 (ms 単位)。0 で無効 */
static int max_messages   = 12;
static int idle_quiesce_ms = 300;

static int             messages_processed = 0;
static pthread_mutex_t counter_mu         = PTHREAD_MUTEX_INITIALIZER;
volatile int           global_shutdown    = 0;   /* extern visible */
static pthread_mutex_t print_mu           = PTHREAD_MUTEX_INITIALIZER;

typedef enum { V_NIL, V_INT, V_FLOAT, V_STR, V_OBJ } vtag_t;
typedef struct {
  vtag_t tag;
  long   i;
  double f;
  const char* s;
  int    obj_id;
} value_t;

static value_t mk_int(long n)        { value_t v={0}; v.tag=V_INT;   v.i=n;     return v; }
static value_t mk_float(double n)    { value_t v={0}; v.tag=V_FLOAT; v.f=n;     return v; }
static value_t mk_str(const char* s) { value_t v={0}; v.tag=V_STR;   v.s=s;     return v; }
static value_t mk_obj(int id)        { value_t v={0}; v.tag=V_OBJ;   v.obj_id=id; return v; }

static int truthy(value_t v) {
  switch (v.tag) {
  case V_INT:   return v.i   != 0;
  case V_FLOAT: return v.f != 0.0;
  case V_STR:   return v.s != NULL && v.s[0] != '\0';
  case V_OBJ:   return v.obj_id >= 0;
  default:      return 0;
  }
}

static const char* v_to_cstr(value_t v, char* tmp, size_t n) {
  switch (v.tag) {
  case V_STR:   return v.s ? v.s : "";
  case V_INT:   snprintf(tmp, n, "%ld", v.i); return tmp;
  case V_FLOAT: snprintf(tmp, n, "%g",  v.f); return tmp;
  case V_OBJ:   snprintf(tmp, n, "<obj %d>", v.obj_id); return tmp;
  default:      return "<nil>";
  }
}

static value_t v_binop(const char* op, value_t a, value_t b) {
  if (strcmp(op, "+") == 0) {
    if (a.tag == V_STR || b.tag == V_STR) {
      char ab[64], bb[64];
      const char* as = v_to_cstr(a, ab, sizeof ab);
      const char* bs = v_to_cstr(b, bb, sizeof bb);
      char* r = (char*)malloc(strlen(as) + strlen(bs) + 1);
      strcpy(r, as); strcat(r, bs);
      return mk_str(r);
    }
    if (a.tag == V_INT && b.tag == V_INT) return mk_int(a.i + b.i);
    double af = (a.tag == V_FLOAT) ? a.f : (double)a.i;
    double bf = (b.tag == V_FLOAT) ? b.f : (double)b.i;
    return mk_float(af + bf);
  }
  if (strcmp(op, "-") == 0 || strcmp(op, "*") == 0 || strcmp(op, "/") == 0) {
    double af = (a.tag == V_FLOAT) ? a.f : (double)a.i;
    double bf = (b.tag == V_FLOAT) ? b.f : (double)b.i;
    double r = 0;
    switch (op[0]) {
    case '-': r = af - bf; break;
    case '*': r = af * bf; break;
    case '/': r = af / bf; break;
    }
    if (a.tag == V_INT && b.tag == V_INT) return mk_int((long)r);
    return mk_float(r);
  }
  /* 比較 */
  double af = (a.tag == V_FLOAT) ? a.f : (double)a.i;
  double bf = (b.tag == V_FLOAT) ? b.f : (double)b.i;
  int r = 0;
  if      (strcmp(op, "==") == 0) r = (af == bf);
  else if (strcmp(op, "!=") == 0) r = (af != bf);
  else if (strcmp(op, "<")  == 0) r = (af <  bf);
  else if (strcmp(op, "<=") == 0) r = (af <= bf);
  else if (strcmp(op, ">")  == 0) r = (af >  bf);
  else if (strcmp(op, ">=") == 0) r = (af >= bf);
  return mk_int(r);
}

static void v_print(value_t v) {
  char tmp[128];
  pthread_mutex_lock(&print_mu);
  printf("%s\n", v_to_cstr(v, tmp, sizeof tmp));
  fflush(stdout);
  pthread_mutex_unlock(&print_mu);
}

typedef struct {
  int         sender;
  int         receiver;
  const char* method;
  int         n_args;
  value_t     args[MAX_ARGS];
} message_t;

typedef struct {
  message_t       msgs[MAX_MAILBOX];
  int             head;   /* index of next dequeue */
  int             tail;   /* index of next enqueue */
  pthread_mutex_t mu;
  pthread_cond_t  cv;
} mailbox_t;

typedef struct {
  int       class_id;
  value_t   fields[MAX_FIELDS];
  mailbox_t mbox;
  pthread_t thread;
  int       started;
} object_t;

static object_t        objects[MAX_OBJECTS];
static int             n_objects  = 0;
static pthread_mutex_t objects_mu = PTHREAD_MUTEX_INITIALIZER;

static void mailbox_init(mailbox_t* mb) {
  mb->head = mb->tail = 0;
  pthread_mutex_init(&mb->mu, NULL);
  pthread_cond_init(&mb->cv, NULL);
}

/* 全アクターを起こし、グローバル停止を伝播させる */
void wake_all_actors(void) {
  pthread_mutex_lock(&objects_mu);
  int n = n_objects;
  pthread_mutex_unlock(&objects_mu);
  for (int i = 0; i < n; i++) {
    pthread_mutex_lock(&objects[i].mbox.mu);
    pthread_cond_broadcast(&objects[i].mbox.cv);
    pthread_mutex_unlock(&objects[i].mbox.mu);
  }
}

void abcl_shutdown(void) {
  global_shutdown = 1;
  wake_all_actors();
}

/* 受信側のメールボックスへ非同期送信 (extern 公開) */
void enqueue(int sender, int receiver, const char* method,
             int n_args, value_t* args) {
  if (receiver < 0) return;
  pthread_mutex_lock(&objects_mu);
  int n = n_objects;
  pthread_mutex_unlock(&objects_mu);
  if (receiver >= n) return;

  mailbox_t* mb = &objects[receiver].mbox;
  pthread_mutex_lock(&mb->mu);
  if (mb->tail - mb->head < MAX_MAILBOX) {
    int idx = mb->tail % MAX_MAILBOX;
    mb->msgs[idx].sender   = sender;
    mb->msgs[idx].receiver = receiver;
    mb->msgs[idx].method   = method;
    mb->msgs[idx].n_args   = n_args;
    for (int i = 0; i < n_args && i < MAX_ARGS; i++)
      mb->msgs[idx].args[i] = args[i];
    mb->tail++;
    pthread_cond_signal(&mb->cv);
  }
  pthread_mutex_unlock(&mb->mu);
}

/* 静止検出ウォッチドッグ：messages_processed が一定時間更新されなければ停止 */
static void* watchdog_main(void* arg) {
  (void)arg;
  if (idle_quiesce_ms <= 0) return NULL;
  int last = -1;
  int idle_ms = 0;
  while (!global_shutdown) {
    struct timespec ts = {0, 50 * 1000 * 1000}; /* 50ms */
    nanosleep(&ts, NULL);
    pthread_mutex_lock(&counter_mu);
    int now = messages_processed;
    pthread_mutex_unlock(&counter_mu);
    if (now == last) {
      idle_ms += 50;
      if (idle_ms >= idle_quiesce_ms) {
        abcl_shutdown();
        break;
      }
    } else {
      idle_ms = 0;
      last = now;
    }
  }
  return NULL;
}
|}

(* ---------- プログラム全体 ---------- *)
let gen_program ?(max_messages = 12) (p : program) : string =
  Buffer.clear buf;
  let cs = classes_of p in
  let gs = globals_of p in

  emit runtime_prelude;
  emit "\n";
  emitf "/* runtime cap override */\n__attribute__((constructor)) static void _set_cap(void){ max_messages = %d; if (max_messages == 0) idle_quiesce_ms = 0; }\n\n" max_messages;

  (* 外部ビルトインの前方宣言 *)
  let externs = collect_externs p in
  if externs <> [] then begin
    emit "/* extern built-ins */\n";
    List.iter (fun f ->
      emitf "extern value_t %s(int n_args, value_t* args);\n" f
    ) externs;
    emit "\n"
  end;

  (* class id *)
  List.iteri (fun i (c : class_decl) -> emitf "#define CLASS_%s %d\n" c.cname i) cs;
  emit "\n";

  (* 前方宣言 *)
  List.iter
    (fun (c : class_decl) ->
      emitf "static void dispatch_%s(int, int, const char*, value_t*, int);\n" c.cname)
    cs;
  emit "static int create_obj(int class_id, int n_args, value_t* args);\n";
  emit "static int alloc_obj(int class_id, int n_args, value_t* args);\n";
  emit "static void spawn_actor(int id);\n";
  emit "static void* actor_main(void* arg);\n\n";

  (* グローバル変数 (object id を保持) *)
  List.iter
    (fun s ->
      match s.sdesc with
      | VarDecl (x, _) -> emitf "static int g_%s = -1;\n" x
      | _ -> ())
    gs;
  emit "\n";

  (* 各クラスのメソッド・dispatch *)
  List.iter gen_class cs;

  (* dispatch ルータ *)
  emit "static void dispatch(int self_id, int sender_id, const char* method, value_t* args, int n_args) {\n";
  emit "  switch (objects[self_id].class_id) {\n";
  List.iter
    (fun (c : class_decl) ->
      emitf "  case CLASS_%s: dispatch_%s(self_id, sender_id, method, args, n_args); break;\n"
        c.cname c.cname)
    cs;
  emit "  default: fprintf(stderr, \"unknown class %d\\n\", objects[self_id].class_id);\n";
  emit "  }\n";
  emit "}\n\n";

  (* クラスごとのフィールド初期化ディスパッチ *)
  emit "static void init_fields(int class_id, int self_id) {\n";
  emit "  switch (class_id) {\n";
  List.iter
    (fun (c : class_decl) ->
      emitf "  case CLASS_%s: init_fields_%s(self_id); break;\n" c.cname c.cname)
    cs;
  emit "  default: break;\n";
  emit "  }\n";
  emit "}\n\n";

  (* オブジェクト確保 (mailbox 初期化＋init 投函のみ。スレッド未起動) *)
  emit "static int alloc_obj(int class_id, int n_args, value_t* args) {\n";
  emit "  pthread_mutex_lock(&objects_mu);\n";
  emit "  int id = n_objects++;\n";
  emit "  pthread_mutex_unlock(&objects_mu);\n";
  emit "  objects[id].class_id = class_id;\n";
  emit "  for (int i = 0; i < MAX_FIELDS; i++) objects[id].fields[i] = mk_int(0L);\n";
  emit "  init_fields(class_id, id);\n";
  emit "  mailbox_init(&objects[id].mbox);\n";
  emit "  objects[id].started = 0;\n";
  emit "  enqueue(-1, id, \"init\", n_args, args);\n";
  emit "  return id;\n";
  emit "}\n\n";

  emit "static void spawn_actor(int id) {\n";
  emit "  if (objects[id].started) return;\n";
  emit "  objects[id].started = 1;\n";
  emit "  pthread_create(&objects[id].thread, NULL, actor_main, (void*)(intptr_t)id);\n";
  emit "}\n\n";

  (* メソッド実行中の new もスレッド即起動 *)
  emit "static int create_obj(int class_id, int n_args, value_t* args) {\n";
  emit "  int id = alloc_obj(class_id, n_args, args);\n";
  emit "  spawn_actor(id);\n";
  emit "  return id;\n";
  emit "}\n\n";

  (* アクター本体ループ *)
  emit "static void* actor_main(void* arg) {\n";
  emit "  int self_id = (int)(intptr_t)arg;\n";
  emit "  mailbox_t* mb = &objects[self_id].mbox;\n";
  emit "  while (1) {\n";
  emit "    message_t m;\n";
  emit "    pthread_mutex_lock(&mb->mu);\n";
  emit "    while (mb->head == mb->tail && !global_shutdown) {\n";
  emit "      pthread_cond_wait(&mb->cv, &mb->mu);\n";
  emit "    }\n";
  emit "    if (global_shutdown) {\n";
  emit "      pthread_mutex_unlock(&mb->mu);\n";
  emit "      break;\n";
  emit "    }\n";
  emit "    m = mb->msgs[mb->head % MAX_MAILBOX];\n";
  emit "    mb->head++;\n";
  emit "    pthread_mutex_unlock(&mb->mu);\n\n";
  emit "    pthread_mutex_lock(&counter_mu);\n";
  emit "    int idx = ++messages_processed;\n";
  emit "    pthread_mutex_unlock(&counter_mu);\n";
  emit "    if (max_messages > 0 && idx > max_messages) {\n";
  emit "      pthread_mutex_lock(&print_mu);\n";
  emit "      printf(\"[runtime] message cap reached (%d)\\n\", max_messages);\n";
  emit "      fflush(stdout);\n";
  emit "      pthread_mutex_unlock(&print_mu);\n";
  emit "      abcl_shutdown();\n";
  emit "      break;\n";
  emit "    }\n";
  emit "    dispatch(self_id, m.sender, m.method, m.args, m.n_args);\n";
  emit "  }\n";
  emit "  return NULL;\n";
  emit "}\n\n";

  (* main : 全 global を alloc → 全 actor を spawn → 全 join *)
  emit "int main(void) {\n";
  let g_ctx = { cname = ""; fields = []; params = []; locals = [] } in
  emit "  /* phase 1: 全 global VarDecl を alloc (スレッド未起動) */\n";
  List.iter
    (fun s ->
      match s.sdesc with
      | VarDecl (x, { desc = New (cls, args); _ }) ->
          let n = List.length args in
          let argstr =
            if n = 0 then "NULL"
            else
              "(value_t[]){"
              ^ String.concat ", " (List.map (gen_expr ~ctx:g_ctx) args)
              ^ "}"
          in
          emitf "  g_%s = alloc_obj(CLASS_%s, %d, %s);\n" x cls n argstr
      | VarDecl (x, e) ->
          emitf "  /* global %s = %s (non-object globals not supported) */\n"
            x (Ast.string_of_expr e)
      | _ -> ())
    gs;
  emit "\n  /* phase 2: 全アクターを起動 (相互参照可) */\n";
  emit "  pthread_mutex_lock(&objects_mu);\n";
  emit "  int initial = n_objects;\n";
  emit "  pthread_mutex_unlock(&objects_mu);\n";
  emit "  for (int i = 0; i < initial; i++) spawn_actor(i);\n\n";
  emit "  /* phase 3: 残りの top-level 文 (Send/CallStmt) をソース順で実行 */\n";
  List.iter
    (fun s ->
      match s.sdesc with
      | VarDecl _ -> ()
      | Send (tgt, meth, args) | UnsafeSend (tgt, meth, args) ->
          let rid = target_id ~ctx:g_ctx tgt in
          let n   = List.length args in
          let argstr =
            if n = 0 then "NULL"
            else
              "(value_t[]){"
              ^ String.concat ", " (List.map (gen_expr ~ctx:g_ctx) args)
              ^ "}"
          in
          emitf "  enqueue(-1, %s, \"%s\", %d, %s);\n" rid meth n argstr
      | CallStmt (f, args) when f = "print" ->
          let arg = List.hd args in
          emitf "  v_print(%s);\n" (gen_expr ~ctx:g_ctx arg)
      | CallStmt (f, args) ->
          let n = List.length args in
          let argstr =
            if n = 0 then "NULL"
            else
              "(value_t[]){"
              ^ String.concat ", " (List.map (gen_expr ~ctx:g_ctx) args)
              ^ "}"
          in
          emitf "  %s(%d, %s);\n" (mangle f) n argstr
      | _ -> ())
    gs;
  emit "\n  /* phase 4: 静止検出ウォッチドッグ */\n";
  emit "  pthread_t wd;\n";
  emit "  pthread_create(&wd, NULL, watchdog_main, NULL);\n\n";
  emit "  /* 全アクターの終了を待つ。new で増えても join しきる */\n";
  emit "  int joined = 0;\n";
  emit "  while (1) {\n";
  emit "    pthread_mutex_lock(&objects_mu);\n";
  emit "    int total = n_objects;\n";
  emit "    pthread_mutex_unlock(&objects_mu);\n";
  emit "    if (joined >= total) break;\n";
  emit "    for (int i = joined; i < total; i++) {\n";
  emit "      pthread_join(objects[i].thread, NULL);\n";
  emit "    }\n";
  emit "    joined = total;\n";
  emit "  }\n";
  emit "  global_shutdown = 1;\n";
  emit "  pthread_join(wd, NULL);\n";
  emit "  return 0;\n";
  emit "}\n";
  Buffer.contents buf

(* ===================== Xinu 用ランタイム ===================== *)

let runtime_prelude_xinu = {|#include <stddef.h>
#include <kernel.h>
#include <thread.h>
#include <semaphore.h>
#include <stdio.h>
#include <string.h>

#define MAX_MAILBOX 16
#define MAX_OBJECTS 16
#define MAX_FIELDS  16
#define MAX_ARGS    8

static int max_messages       = 20;
static int messages_processed = 0;
volatile int global_shutdown  = 0;
static semaphore counter_mu;
static semaphore print_mu;

typedef enum { V_NIL, V_INT, V_FLOAT, V_STR, V_OBJ } vtag_t;
typedef struct {
  vtag_t      tag;
  long        i;
  double      f;
  const char *s;
  int         obj_id;
} value_t;

static value_t mk_int(long n)        { value_t v; v.tag=V_INT;   v.i=n;   v.f=0; v.s=0; v.obj_id=0; return v; }
static value_t mk_float(double n)    { value_t v; v.tag=V_FLOAT; v.f=n;   v.i=0; v.s=0; v.obj_id=0; return v; }
static value_t mk_str(const char *s) { value_t v; v.tag=V_STR;   v.s=s;   v.i=0; v.f=0; v.obj_id=0; return v; }
static value_t mk_obj(int id)        { value_t v; v.tag=V_OBJ;   v.obj_id=id; v.i=0; v.f=0; v.s=0; return v; }

static int truthy(value_t v) {
  switch (v.tag) {
  case V_INT:   return v.i != 0;
  case V_FLOAT: return v.f != 0.0;
  case V_STR:   return v.s != NULL && v.s[0] != '\0';
  case V_OBJ:   return v.obj_id >= 0;
  default:      return 0;
  }
}

static value_t v_binop(const char *op, value_t a, value_t b) {
  long ai = (a.tag == V_INT) ? a.i : (a.tag == V_FLOAT ? (long)a.f : 0);
  long bi = (b.tag == V_INT) ? b.i : (b.tag == V_FLOAT ? (long)b.f : 0);
  if (op[0] == '+' && op[1] == '\0') return mk_int(ai + bi);
  if (op[0] == '-' && op[1] == '\0') return mk_int(ai - bi);
  if (op[0] == '*' && op[1] == '\0') return mk_int(ai * bi);
  if (op[0] == '/' && op[1] == '\0') return mk_int(bi != 0 ? ai / bi : 0);
  if (op[0] == '=' && op[1] == '=')  return mk_int(ai == bi);
  if (op[0] == '!' && op[1] == '=')  return mk_int(ai != bi);
  if (op[0] == '<' && op[1] == '=')  return mk_int(ai <= bi);
  if (op[0] == '>' && op[1] == '=')  return mk_int(ai >= bi);
  if (op[0] == '<' && op[1] == '\0') return mk_int(ai <  bi);
  if (op[0] == '>' && op[1] == '\0') return mk_int(ai >  bi);
  return mk_int(0);
}

static void v_print(value_t v) {
  wait(print_mu);
  switch (v.tag) {
  case V_STR: kprintf("%s\r\n", v.s ? v.s : ""); break;
  case V_INT: kprintf("%d\r\n", (int)v.i);       break;
  case V_OBJ: kprintf("<obj %d>\r\n", v.obj_id); break;
  default:    kprintf("<nil>\r\n");              break;
  }
  signal(print_mu);
}

typedef struct {
  int         sender;
  int         receiver;
  const char *method;
  int         n_args;
  value_t     args[MAX_ARGS];
} message_t;

typedef struct {
  message_t msgs[MAX_MAILBOX];
  int       head, tail;
  semaphore mu;
  semaphore items;
} mailbox_t;

typedef struct {
  int       class_id;
  value_t   fields[MAX_FIELDS];
  mailbox_t mbox;
  tid_typ   tid;
  int       started;
} object_t;

static object_t objects[MAX_OBJECTS];
static int      n_objects = 0;
static semaphore objects_mu;

static void mailbox_init(mailbox_t *mb) {
  mb->head = 0;
  mb->tail = 0;
  mb->mu    = semcreate(1);
  mb->items = semcreate(0);
}

void wake_all_actors(void) {
  int i;
  for (i = 0; i < n_objects; i++) {
    /* items を 1 増やすことで wait() しているアクターを起こす */
    signal(objects[i].mbox.items);
  }
}

void abcl_shutdown(void) {
  global_shutdown = 1;
  wake_all_actors();
}

/* Xinu の queue.h にある enqueue() と名前が衝突するのでリネーム。
   以降 abcl 側のコードでは enqueue マクロで本関数を呼ぶ。 */
void abcl_enqueue(int sender, int receiver, const char *method,
                  int n_args, value_t *args) {
  if (receiver < 0 || receiver >= n_objects) return;
  mailbox_t *mb = &objects[receiver].mbox;
  wait(mb->mu);
  if (mb->tail - mb->head < MAX_MAILBOX) {
    int idx = mb->tail % MAX_MAILBOX;
    int i;
    mb->msgs[idx].sender   = sender;
    mb->msgs[idx].receiver = receiver;
    mb->msgs[idx].method   = method;
    mb->msgs[idx].n_args   = n_args;
    for (i = 0; i < n_args && i < MAX_ARGS; i++)
      mb->msgs[idx].args[i] = args[i];
    mb->tail++;
    signal(mb->mu);
    signal(mb->items);
  } else {
    signal(mb->mu);
  }
}

/* 以降の生成コードでは abcl_enqueue を enqueue として書く */
#define enqueue abcl_enqueue
|}

(* ---------- Xinu 用プログラム生成 ---------- *)
let gen_program_xinu ?(max_messages = 20) (p : program) : string =
  Buffer.clear buf;
  let cs = classes_of p in
  let gs = globals_of p in

  emit runtime_prelude_xinu;
  emit "\n";
  emitf "/* runtime cap override */\nstatic int _abcl_cap = %d;\n\n" max_messages;

  (* 外部ビルトインの前方宣言 *)
  let externs = collect_externs p in
  if externs <> [] then begin
    emit "/* extern built-ins */\n";
    List.iter (fun f ->
      emitf "extern value_t %s(int n_args, value_t* args);\n" f
    ) externs;
    emit "\n"
  end;

  (* class id *)
  List.iteri (fun i (c : class_decl) -> emitf "#define CLASS_%s %d\n" c.cname i) cs;
  emit "\n";

  (* 前方宣言 *)
  List.iter
    (fun (c : class_decl) ->
      emitf "static void dispatch_%s(int, int, const char*, value_t*, int);\n" c.cname)
    cs;
  emit "static void dispatch(int, int, const char*, value_t*, int);\n";
  emit "static int  alloc_obj(int class_id, int n_args, value_t* args);\n";
  emit "static void spawn_actor(int id);\n";
  emit "static int  create_obj(int class_id, int n_args, value_t* args);\n";
  emit "thread      abcl_actor_main(int self_id);\n\n";

  (* グローバル変数 (object id を保持) *)
  List.iter
    (fun s ->
      match s.sdesc with
      | VarDecl (x, _) -> emitf "static int g_%s = -1;\n" x
      | _ -> ())
    gs;
  emit "\n";

  (* 各クラスの定義 (POSIX 版と同じヘルパを再利用) *)
  List.iter gen_class cs;

  (* dispatch ルータ *)
  emit "static void dispatch(int self_id, int sender_id, const char* method, value_t* args, int n_args) {\n";
  emit "  switch (objects[self_id].class_id) {\n";
  List.iter
    (fun (c : class_decl) ->
      emitf "  case CLASS_%s: dispatch_%s(self_id, sender_id, method, args, n_args); break;\n"
        c.cname c.cname)
    cs;
  emit "  default: kprintf(\"unknown class %d\\r\\n\", objects[self_id].class_id);\n";
  emit "  }\n";
  emit "}\n\n";

  (* init_fields ディスパッチ *)
  emit "static void init_fields(int class_id, int self_id) {\n";
  emit "  switch (class_id) {\n";
  List.iter
    (fun (c : class_decl) ->
      emitf "  case CLASS_%s: init_fields_%s(self_id); break;\n" c.cname c.cname)
    cs;
  emit "  default: break;\n";
  emit "  }\n";
  emit "}\n\n";

  (* alloc_obj / spawn / create_obj *)
  emit "static int alloc_obj(int class_id, int n_args, value_t* args) {\n";
  emit "  int id;\n  int i;\n";
  emit "  wait(objects_mu);\n";
  emit "  id = n_objects++;\n";
  emit "  signal(objects_mu);\n";
  emit "  objects[id].class_id = class_id;\n";
  emit "  for (i = 0; i < MAX_FIELDS; i++) objects[id].fields[i] = mk_int(0L);\n";
  emit "  init_fields(class_id, id);\n";
  emit "  mailbox_init(&objects[id].mbox);\n";
  emit "  objects[id].started = 0;\n";
  emit "  enqueue(-1, id, \"init\", n_args, args);\n";
  emit "  return id;\n";
  emit "}\n\n";

  emit "static void spawn_actor(int id) {\n";
  emit "  if (objects[id].started) return;\n";
  emit "  objects[id].started = 1;\n";
  emit "  objects[id].tid = create((void*)abcl_actor_main, 4096, INITPRIO,\n";
  emit "                            \"abcl-actor\", 1, id);\n";
  emit "  ready(objects[id].tid, RESCHED_NO);\n";
  emit "}\n\n";

  emit "static int create_obj(int class_id, int n_args, value_t* args) {\n";
  emit "  int id = alloc_obj(class_id, n_args, args);\n";
  emit "  spawn_actor(id);\n";
  emit "  return id;\n";
  emit "}\n\n";

  (* actor 本体 (Xinu process) *)
  emit "thread abcl_actor_main(int self_id) {\n";
  emit "  mailbox_t* mb = &objects[self_id].mbox;\n";
  emit "  for (;;) {\n";
  emit "    message_t m;\n";
  emit "    int idx;\n";
  emit "    if (global_shutdown) break;\n";
  emit "    wait(mb->items);\n";
  emit "    if (global_shutdown) break;\n";
  emit "    wait(mb->mu);\n";
  emit "    if (mb->head == mb->tail) { signal(mb->mu); continue; }\n";
  emit "    m = mb->msgs[mb->head % MAX_MAILBOX];\n";
  emit "    mb->head++;\n";
  emit "    signal(mb->mu);\n";
  emit "    wait(counter_mu);\n";
  emit "    idx = ++messages_processed;\n";
  emit "    signal(counter_mu);\n";
  emit "    if (_abcl_cap > 0 && idx > _abcl_cap) {\n";
  emit "      wait(print_mu);\n";
  emit "      kprintf(\"[abcl] message cap reached (%d)\\r\\n\", _abcl_cap);\n";
  emit "      signal(print_mu);\n";
  emit "      abcl_shutdown();\n";
  emit "      break;\n";
  emit "    }\n";
  emit "    dispatch(self_id, m.sender, m.method, m.args, m.n_args);\n";
  emit "  }\n";
  emit "  return OK;\n";
  emit "}\n\n";

  (* abcl エントリポイント (Xinu の main から呼ぶ) *)
  emit "thread aipl_main(void) {\n";
  emit "  counter_mu = semcreate(1);\n";
  emit "  print_mu   = semcreate(1);\n";
  emit "  objects_mu = semcreate(1);\n";
  emit "  kprintf(\"\\r\\n[abcl] starting...\\r\\n\");\n";
  let g_ctx = { cname = ""; fields = []; params = []; locals = [] } in
  emit "  /* phase 1: alloc all globals */\n";
  List.iter
    (fun s ->
      match s.sdesc with
      | VarDecl (x, { desc = New (cls, args); _ }) ->
          let n = List.length args in
          let argstr =
            if n = 0 then "NULL"
            else
              "(value_t[]){"
              ^ String.concat ", " (List.map (gen_expr ~ctx:g_ctx) args)
              ^ "}"
          in
          emitf "  g_%s = alloc_obj(CLASS_%s, %d, %s);\n" x cls n argstr
      | _ -> ())
    gs;
  emit "  /* phase 2: spawn actors */\n";
  emit "  {\n";
  emit "    int i, total;\n";
  emit "    wait(objects_mu); total = n_objects; signal(objects_mu);\n";
  emit "    for (i = 0; i < total; i++) spawn_actor(i);\n";
  emit "  }\n";
  emit "  /* phase 3: any non-VarDecl top-level */\n";
  List.iter
    (fun s ->
      match s.sdesc with
      | VarDecl _ -> ()
      | Send (tgt, meth, args) | UnsafeSend (tgt, meth, args) ->
          let rid = target_id ~ctx:g_ctx tgt in
          let n   = List.length args in
          let argstr =
            if n = 0 then "NULL"
            else
              "(value_t[]){"
              ^ String.concat ", " (List.map (gen_expr ~ctx:g_ctx) args)
              ^ "}"
          in
          emitf "  enqueue(-1, %s, \"%s\", %d, %s);\n" rid meth n argstr
      | CallStmt _ ->
          (* Xinu 版では top-level の任意呼び出しはサポート外 (PingPong には不要) *)
          ()
      | _ -> ())
    gs;
  emit "  /* wait for shutdown */\n";
  emit "  while (!global_shutdown) sleep(50);\n";
  emit "  kprintf(\"[abcl] done; messages=%d\\r\\n\", messages_processed);\n";
  emit "  return OK;\n";
  emit "}\n";

  Buffer.contents buf

(* ===================== Python 用ランタイム / コード生成 ===================== *)

let py_runtime_prelude = {|#!/usr/bin/env python3
"""Generated by abcl2c --python from AIPL source."""
import threading
import queue
import sys
import time

# ---------- AIPL Python ランタイム ----------
_objects = {}
_objects_lock = threading.Lock()
_next_id = 0
_global_shutdown = False
_messages_processed = 0
_counter_lock = threading.Lock()
_print_lock = threading.Lock()
_max_messages = 12

def _alloc_id():
    global _next_id
    with _objects_lock:
        i = _next_id
        _next_id += 1
        return i

def _enqueue(sender, receiver, method, args):
    if receiver is None or receiver < 0:
        return
    obj = _objects.get(receiver)
    if obj is not None:
        obj._mailbox.put((sender, method, list(args)))

def _abcl_shutdown():
    global _global_shutdown
    _global_shutdown = True
    with _objects_lock:
        for o in list(_objects.values()):
            o._mailbox.put(None)

def _v_print(v):
    with _print_lock:
        print(v)
        sys.stdout.flush()

def _truthy(v):
    if v is None: return False
    if isinstance(v, (int, float)): return v != 0
    if isinstance(v, str): return len(v) > 0
    return True

def _binop(op, a, b):
    if op == '+':
        if isinstance(a, str) or isinstance(b, str):
            return str(a) + str(b)
        return a + b
    if op == '-': return a - b
    if op == '*': return a * b
    if op == '/':
        try:
            if isinstance(a, int) and isinstance(b, int):
                return a // b if b != 0 else 0
            return a / b if b != 0 else 0.0
        except Exception:
            return 0
    if op == '==': return 1 if a == b else 0
    if op == '!=': return 1 if a != b else 0
    if op == '<':  return 1 if a <  b else 0
    if op == '<=': return 1 if a <= b else 0
    if op == '>':  return 1 if a >  b else 0
    if op == '>=': return 1 if a >= b else 0
    return 0

class _Actor:
    def __init__(self, init_args):
        self.id = _alloc_id()
        self._mailbox = queue.Queue()
        self._thread = None
        with _objects_lock:
            _objects[self.id] = self
        self._init_fields()
        _enqueue(-1, self.id, 'init', list(init_args))

    def _init_fields(self):
        pass

    def _dispatch(self, sender_id, method, args):
        pass

    def _actor_main(self):
        global _messages_processed
        while True:
            msg = self._mailbox.get()
            if msg is None or _global_shutdown:
                break
            sender_id, method, args = msg
            with _counter_lock:
                _messages_processed += 1
                idx = _messages_processed
            if _max_messages > 0 and idx > _max_messages:
                _v_print("[runtime] message cap reached (%d)" % _max_messages)
                _abcl_shutdown()
                break
            self._dispatch(sender_id, method, args)

    def _spawn(self):
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._actor_main, daemon=True)
        self._thread.start()

def _create_obj(cls, init_args):
    """メソッド内で new されたオブジェクトを alloc + spawn する"""
    o = cls(list(init_args))
    o._spawn()
    return o.id

# ---------- 数学ビルトイン (cos/sin は --python では float ラジアン) ----------
import math
def b_cos(angle): return math.cos(angle)
def b_sin(angle): return math.sin(angle)

# ---------- tkinter GUI ランタイム ----------
try:
    import tkinter as _tk
    _has_tk = True
except ImportError:
    _has_tk = False

_gui_w = 640
_gui_h = 480
_gui_title = 'AIPL Python'
_gui_lines = {}
_gui_lines_lock = threading.Lock()
_gui_buttons = []
_gui_tickers = []
_gui_root = None
_gui_canvas = None
_gui_lineids = {}

def gui_open(w=640, h=480, title=0):
    global _gui_w, _gui_h
    _gui_w = int(w)
    _gui_h = int(h)
    return None

# 哲学者問題の状態
_gui_phils = []
_gui_forks = []
_gui_phil_lock = threading.Lock()
_gui_phil_canvas_ids = {}
_gui_fork_canvas_ids = {}

def gui_dining_init(N):
    global _gui_phils, _gui_forks
    N = int(N)
    cx_c, cy_c = 320, 220
    R_phil = 130
    phils = []
    for i in range(N):
        a = -math.pi / 2 + 2 * math.pi * i / N
        phils.append({
            'cx': cx_c + math.cos(a) * R_phil,
            'cy': cy_c + math.sin(a) * R_phil,
            'radius': 24,
            'state': 0,
        })
    forks = []
    for i in range(N):
        a_idx = (i - 1 + N) % N
        b_idx = i
        if phils[a_idx]['cx'] <= phils[b_idx]['cx']:
            leftside, rightside = a_idx, b_idx
        else:
            leftside, rightside = b_idx, a_idx
        lx, ly = phils[leftside]['cx'],  phils[leftside]['cy']
        rx, ry = phils[rightside]['cx'], phils[rightside]['cy']
        mx, my = (lx + rx) / 2.0, (ly + ry) / 2.0
        dx, dy = rx - lx, ry - ly
        L = math.sqrt(dx * dx + dy * dy)
        if L > 0:
            ux, uy = dx / L, dy / L
        else:
            ux, uy = 1.0, 0.0
        half = 18.0
        forks.append({
            'leftside': leftside,
            'rightside': rightside,
            'xl': mx - ux * half, 'yl': my - uy * half,
            'xr': mx + ux * half, 'yr': my + uy * half,
            'held': 0, 'holder': -1,
        })
    with _gui_phil_lock:
        _gui_phils = phils
        _gui_forks = forks
    return None

def gui_set_phil(idx, state):
    idx = int(idx)
    with _gui_phil_lock:
        if 0 <= idx < len(_gui_phils):
            _gui_phils[idx]['state'] = int(state)
    return None

def gui_set_fork_held(idx, holder):
    idx = int(idx)
    with _gui_phil_lock:
        if 0 <= idx < len(_gui_forks):
            _gui_forks[idx]['held']   = 1
            _gui_forks[idx]['holder'] = int(holder)
    return None

def gui_set_fork_free(idx):
    idx = int(idx)
    with _gui_phil_lock:
        if 0 <= idx < len(_gui_forks):
            _gui_forks[idx]['held']   = 0
            _gui_forks[idx]['holder'] = -1
    return None

# ---------- 有限バッファ問題 ----------
_PRODUCER_PALETTE = [(220,90,90), (90,200,130), (90,140,230),
                     (220,180,90), (180,90,220), (90,200,220)]
_gui_slots = []
_gui_producers = []
_gui_consumers = []
_gui_buf_capacity = 0
_gui_buf_head = 0
_gui_buf_tail = 0
_gui_buf_lock = threading.Lock()
_gui_slot_canvas_ids = {}
_gui_slot_inner_ids = {}
_gui_actor_canvas_ids = {}

def gui_buf_setup(cap, npr, nco, *args):
    global _gui_buf_capacity, _gui_slots, _gui_producers, _gui_consumers
    global _gui_buf_head, _gui_buf_tail
    cap = int(cap); npr = int(npr); nco = int(nco)
    if cap > 32: cap = 32
    if npr > 6:  npr = 6
    if nco > 6:  nco = 6
    top_y, bot_y = 80, 320
    actor_margin = 90
    avail = _gui_w - 2 * actor_margin
    slot_w = max(14, min(30, avail // cap if cap > 0 else 24))
    slot_h = min(36, slot_w + 8)
    total = slot_w * cap
    start_x = (_gui_w - total) // 2
    slot_y = (top_y + bot_y) // 2 - slot_h // 2
    slots = []
    for i in range(cap):
        slots.append({'filled': 0, 'producer_id': -1,
                      'x': start_x + i * slot_w, 'y': slot_y,
                      'w': slot_w - 2, 'h': slot_h - 2})
    producers, consumers = [], []
    for i in range(npr):
        if npr <= 1: yy = (top_y + bot_y) // 2
        else:        yy = top_y + i * (bot_y - top_y) // (npr - 1)
        producers.append({'state': 0, 'cx': 30, 'cy': yy, 'radius': 22})
    for i in range(nco):
        if nco <= 1: yy = (top_y + bot_y) // 2
        else:        yy = top_y + i * (bot_y - top_y) // (nco - 1)
        consumers.append({'state': 0, 'cx': _gui_w - 30, 'cy': yy, 'radius': 22})
    with _gui_buf_lock:
        _gui_buf_capacity = cap
        _gui_buf_head = 0; _gui_buf_tail = 0
        _gui_slots = slots
        _gui_producers = producers
        _gui_consumers = consumers
    return None

def gui_buf_put(producer_id):
    global _gui_buf_tail
    pid = int(producer_id)
    with _gui_buf_lock:
        if _gui_buf_capacity <= 0: return None
        slot = _gui_buf_tail % _gui_buf_capacity
        _gui_slots[slot]['filled']      = 1
        _gui_slots[slot]['producer_id'] = pid
        _gui_buf_tail += 1
    return None

def gui_buf_take(*args):
    global _gui_buf_head
    with _gui_buf_lock:
        if _gui_buf_capacity <= 0: return None
        slot = _gui_buf_head % _gui_buf_capacity
        _gui_slots[slot]['filled']      = 0
        _gui_slots[slot]['producer_id'] = -1
        _gui_buf_head += 1
    return None

def gui_set_actor(idx, type_, state):
    idx = int(idx); type_ = int(type_); state = int(state)
    with _gui_buf_lock:
        if type_ == 0 and 0 <= idx < len(_gui_producers):
            _gui_producers[idx]['state'] = state
        elif type_ == 1 and 0 <= idx < len(_gui_consumers):
            _gui_consumers[idx]['state'] = state
    return None

# ---------- スライダー ----------
_gui_sliders_config = []
_gui_slider_values = {}
_gui_slider_lock = threading.Lock()

def gui_add_slider(track_id, x, y, w, h, mn, mx, init, *rest):
    label = ''
    if len(rest) >= 4 and isinstance(rest[3], str):
        label = rest[3]
    track_id = int(track_id); init = int(init)
    _gui_sliders_config.append({'track_id': track_id,
                                 'x': int(x), 'y': int(y),
                                 'w': int(w), 'h': int(h),
                                 'min': int(mn), 'max': int(mx),
                                 'init': init, 'label': label})
    with _gui_slider_lock:
        _gui_slider_values[track_id] = init
    return None

def gui_slider_value(track_id):
    with _gui_slider_lock:
        return _gui_slider_values.get(int(track_id), 0)

def gui_set_line(idx, x1, y1, x2, y2, r=200, g=220, b=255):
    with _gui_lines_lock:
        _gui_lines[int(idx)] = (float(x1), float(y1), float(x2), float(y2),
                                int(r), int(g), int(b))
    return None

def gui_register_ticker(target):
    if isinstance(target, int):
        _gui_tickers.append(target)
    return None

def gui_add_button(label, x, y, w, h, target, method):
    _gui_buttons.append((str(label), int(x), int(y), int(w), int(h),
                         int(target), str(method)))
    return None

def _gui_close_handler():
    _abcl_shutdown()
    if _gui_root is not None:
        try: _gui_root.destroy()
        except Exception: pass

def gui_run(*args):
    global _gui_root, _gui_canvas
    if not _has_tk:
        print('[gui] tkinter not available', file=sys.stderr)
        _abcl_shutdown()
        return None
    # actor 達が init で button/ticker を登録するのを少し待つ
    time.sleep(0.15)
    _gui_root = _tk.Tk()
    _gui_root.title(_gui_title)
    _gui_canvas = _tk.Canvas(_gui_root, width=_gui_w, height=_gui_h,
                             bg='#10141e', highlightthickness=0)
    _gui_canvas.pack()
    # 登録済みボタンを配置
    for label, x, y, w, h, target, method in list(_gui_buttons):
        btn = _tk.Button(_gui_root, text=label,
                         command=(lambda t=target, m=method:
                                  _enqueue(-1, t, m, [])))
        _gui_canvas.create_window(x + w // 2, y + h // 2,
                                  window=btn, width=w, height=h)
    # スライダー (tk.Scale)
    _slider_widgets = []
    for cfg in list(_gui_sliders_config):
        tid = cfg['track_id']
        def _make_handler(track_id):
            def on_change(val):
                with _gui_slider_lock:
                    _gui_slider_values[track_id] = int(float(val))
            return on_change
        sc = _tk.Scale(_gui_root, from_=cfg['min'], to=cfg['max'],
                       orient='horizontal', length=cfg['w'],
                       command=_make_handler(tid),
                       label=cfg['label'])
        sc.set(cfg['init'])
        _gui_canvas.create_window(cfg['x'], cfg['y'], window=sc, anchor='nw')
        _slider_widgets.append(sc)
    _gui_root.protocol('WM_DELETE_WINDOW', _gui_close_handler)

    def _gui_step():
        if _global_shutdown:
            _gui_close_handler()
            return
        # tick 配信
        for tid in list(_gui_tickers):
            _enqueue(-1, tid, 'tick', [])
        # 線分の更新 (Rotate4Lines 等)
        with _gui_lines_lock:
            snap = dict(_gui_lines)
        for idx, (x1, y1, x2, y2, r, g, b) in snap.items():
            color = '#%02x%02x%02x' % (max(0, min(r, 255)),
                                        max(0, min(g, 255)),
                                        max(0, min(b, 255)))
            if idx in _gui_lineids:
                _gui_canvas.coords(_gui_lineids[idx], x1, y1, x2, y2)
                _gui_canvas.itemconfig(_gui_lineids[idx], fill=color)
            else:
                _gui_lineids[idx] = _gui_canvas.create_line(
                    x1, y1, x2, y2, fill=color, width=3)
        # 哲学者問題: フォーク (空 / 右矢印 / 左矢印) と哲学者 (色付き円)
        with _gui_phil_lock:
            phils_snap = list(_gui_phils)
            forks_snap = list(_gui_forks)
        for idx, f in enumerate(forks_snap):
            xl, yl, xr, yr = f['xl'], f['yl'], f['xr'], f['yr']
            if not f['held']:
                color = '#888899'
                arrow = 'none'
            elif f['holder'] == f['rightside']:
                color = '#f0c850'   # 占有色 (黄)
                arrow = 'last'      # → rightside (xr 端)
            elif f['holder'] == f['leftside']:
                color = '#f0c850'
                arrow = 'first'     # ← leftside (xl 端)
            else:
                color = '#f0c850'
                arrow = 'none'
            if idx in _gui_fork_canvas_ids:
                _gui_canvas.coords(_gui_fork_canvas_ids[idx], xl, yl, xr, yr)
                _gui_canvas.itemconfig(_gui_fork_canvas_ids[idx],
                                       fill=color, arrow=arrow)
            else:
                _gui_fork_canvas_ids[idx] = _gui_canvas.create_line(
                    xl, yl, xr, yr, fill=color, width=4,
                    arrow=arrow, arrowshape=(16, 18, 7))
        for idx, p in enumerate(phils_snap):
            cx, cy, rad = p['cx'], p['cy'], p['radius']
            st = p['state']
            if st == 0:   color = '#5080e0'
            elif st == 1: color = '#f0c850'
            elif st == 2: color = '#50c878'
            else:         color = '#888'
            if idx in _gui_phil_canvas_ids:
                _gui_canvas.coords(_gui_phil_canvas_ids[idx],
                                   cx - rad, cy - rad, cx + rad, cy + rad)
                _gui_canvas.itemconfig(_gui_phil_canvas_ids[idx], fill=color)
            else:
                _gui_phil_canvas_ids[idx] = _gui_canvas.create_oval(
                    cx - rad, cy - rad, cx + rad, cy + rad,
                    fill=color, outline='#ffffff', width=2)
        # 有限バッファ問題: スロット / producer / consumer
        with _gui_buf_lock:
            slots_snap = list(_gui_slots)
            producers_snap = list(_gui_producers)
            consumers_snap = list(_gui_consumers)
        for i, slot in enumerate(slots_snap):
            x, y, w, h = slot['x'], slot['y'], slot['w'], slot['h']
            if i not in _gui_slot_canvas_ids:
                _gui_slot_canvas_ids[i] = _gui_canvas.create_rectangle(
                    x, y, x + w, y + h, fill='#23262e',
                    outline='#b4b4c8', width=1)
            if slot['filled']:
                pid = slot['producer_id']
                pr, pg, pb = _PRODUCER_PALETTE[pid % 6]
                col = '#%02x%02x%02x' % (pr, pg, pb)
                if i not in _gui_slot_inner_ids:
                    _gui_slot_inner_ids[i] = _gui_canvas.create_rectangle(
                        x + 3, y + 3, x + w - 3, y + h - 3,
                        fill=col, outline='')
                else:
                    _gui_canvas.itemconfig(_gui_slot_inner_ids[i],
                                           state='normal', fill=col)
            else:
                if i in _gui_slot_inner_ids:
                    _gui_canvas.itemconfig(_gui_slot_inner_ids[i],
                                           state='hidden')
        for i, p in enumerate(producers_snap):
            cx, cy, rad = p['cx'], p['cy'], p['radius']
            br, bg_, bb = _PRODUCER_PALETTE[i % 6]
            st = p['state']
            if st == 0:
                cr, cg, cb = br // 3, bg_ // 3, bb // 3
            elif st == 2:
                cr, cg, cb = 240, 200, 80
            else:
                cr, cg, cb = br, bg_, bb
            color = '#%02x%02x%02x' % (cr, cg, cb)
            key = ('p', i)
            if key not in _gui_actor_canvas_ids:
                _gui_actor_canvas_ids[key] = _gui_canvas.create_oval(
                    cx - rad, cy - rad, cx + rad, cy + rad,
                    fill=color, outline='#ffffff', width=2)
            else:
                _gui_canvas.itemconfig(_gui_actor_canvas_ids[key], fill=color)
        for i, c in enumerate(consumers_snap):
            cx, cy, rad = c['cx'], c['cy'], c['radius']
            st = c['state']
            if st == 0:   color = '#3c5050'
            elif st == 1: color = '#5cdc8c'
            elif st == 2: color = '#f0c850'
            else:         color = '#888888'
            key = ('c', i)
            if key not in _gui_actor_canvas_ids:
                _gui_actor_canvas_ids[key] = _gui_canvas.create_oval(
                    cx - rad, cy - rad, cx + rad, cy + rad,
                    fill=color, outline='#ffffff', width=2)
            else:
                _gui_canvas.itemconfig(_gui_actor_canvas_ids[key], fill=color)
        _gui_root.after(16, _gui_step)

    _gui_root.after(50, _gui_step)
    _gui_root.mainloop()
    return None
|}

(* Python 用 expression 生成 *)
let rec gen_expr_py ~ctx (e : expr) : string =
  match e.desc with
  | Int n -> string_of_int n
  | Float f -> Printf.sprintf "%g" f
  | String s -> "\"" ^ String.escaped s ^ "\""
  | Var x ->
      if x = "self"   then "self.id"
      else if x = "sender" then "sender_id"
      else if List.mem x ctx.params then Printf.sprintf "p_%s" x
      else if List.mem x ctx.locals then Printf.sprintf "l_%s" x
      else if List.mem x ctx.fields then Printf.sprintf "self.f_%s" x
      else Printf.sprintf "g_%s" x
  | Binop (op, a, b) ->
      Printf.sprintf "_binop(%S, %s, %s)" op (gen_expr_py ~ctx a) (gen_expr_py ~ctx b)
  | Call ("print", [arg]) ->
      Printf.sprintf "(_v_print(%s) or 0)" (gen_expr_py ~ctx arg)
  | Call (f, args) ->
      let xs = String.concat ", " (List.map (gen_expr_py ~ctx) args) in
      Printf.sprintf "%s(%s)" (mangle f) xs
  | New (cls, args) ->
      let xs = String.concat ", " (List.map (gen_expr_py ~ctx) args) in
      Printf.sprintf "_create_obj(%s, [%s])" cls xs
  | Expr e -> gen_expr_py ~ctx e
  | Array (es, _) ->
      let xs = String.concat ", " (List.map (gen_expr_py ~ctx) es) in
      Printf.sprintf "[%s]" xs

let target_id_py ~ctx tgt =
  match tgt with
  | RemoteTarget _ -> "-1"
  | LocalTarget t ->
      if t = "self"   then "self.id"
      else if t = "sender" then "sender_id"
      else if List.mem t ctx.params then Printf.sprintf "p_%s" t
      else if List.mem t ctx.locals then Printf.sprintf "l_%s" t
      else if List.mem t ctx.fields then Printf.sprintf "self.f_%s" t
      else Printf.sprintf "g_%s" t

let rec gen_stmt_py ~ctx ?(indent=8) (s : stmt) =
  let ind = String.make indent ' ' in
  match s.sdesc with
  | Seq [] -> emitf "%spass\n" ind
  | Seq ss -> List.iter (gen_stmt_py ~ctx ~indent) ss
  | VarDecl (x, e) ->
      let e_py = gen_expr_py ~ctx e in
      ctx.locals <- x :: ctx.locals;
      emitf "%sl_%s = %s\n" ind x e_py
  | Assign (x, e) ->
      let e_py = gen_expr_py ~ctx e in
      if List.mem x ctx.fields then
        emitf "%sself.f_%s = %s\n" ind x e_py
      else if List.mem x ctx.params then
        emitf "%sp_%s = %s\n" ind x e_py
      else if List.mem x ctx.locals then
        emitf "%sl_%s = %s\n" ind x e_py
      else
        emitf "%s# unknown var %s\n" ind x
  | CallStmt ("print", [arg]) ->
      emitf "%s_v_print(%s)\n" ind (gen_expr_py ~ctx arg)
  | CallStmt (f, args) ->
      let xs = String.concat ", " (List.map (gen_expr_py ~ctx) args) in
      emitf "%s%s(%s)\n" ind (mangle f) xs
  | Send (tgt, meth, args) | UnsafeSend (tgt, meth, args) ->
      let rid = target_id_py ~ctx tgt in
      let xs = String.concat ", " (List.map (gen_expr_py ~ctx) args) in
      emitf "%s_enqueue(self.id, %s, %S, [%s])\n" ind rid meth xs
  | If (e, s1, s2) ->
      emitf "%sif _truthy(%s):\n" ind (gen_expr_py ~ctx e);
      gen_stmt_py ~ctx ~indent:(indent + 4) s1;
      (match s2.sdesc with
       | Seq [] -> ()
       | _ ->
         emitf "%selse:\n" ind;
         gen_stmt_py ~ctx ~indent:(indent + 4) s2)
  | While (e, body) ->
      emitf "%swhile _truthy(%s):\n" ind (gen_expr_py ~ctx e);
      gen_stmt_py ~ctx ~indent:(indent + 4) body
  | Become _ -> emitf "%spass  # become unsupported\n" ind
  | Select _ -> emitf "%spass  # select unsupported\n" ind

let gen_class_py (c : class_decl) =
  let fields = fields_of c in
  emitf "class %s(_Actor):\n" c.cname;
  (* _init_fields *)
  emit "    def _init_fields(self):\n";
  (let init_ctx = { cname = c.cname; fields; params = []; locals = [] } in
   let any = ref false in
   List.iter (fun s ->
     match s.sdesc with
     | VarDecl (name, e) ->
         emitf "        self.f_%s = %s\n" name (gen_expr_py ~ctx:init_ctx e);
         any := true
     | _ -> ()
   ) c.fields;
   if not !any then emit "        pass\n");
  emit "\n";
  (* methods *)
  List.iter (fun (md : method_decl) ->
    let ctx = { cname = c.cname; fields; params = md.params; locals = [] } in
    emitf "    def m_%s(self, sender_id, args):\n" md.mname;
    List.iteri (fun i p ->
      emitf "        p_%s = args[%d] if len(args) > %d else 0\n" p i i
    ) md.params;
    (match md.body.sdesc with
     | Seq [] ->
        if md.params = [] then emit "        pass\n"
        else ()  (* params already make body non-empty *)
     | _ -> gen_stmt_py ~ctx ~indent:8 md.body);
    emit "\n"
  ) c.methods;
  (* _dispatch *)
  emit "    def _dispatch(self, sender_id, method, args):\n";
  let has_init = List.exists (fun (md : method_decl) -> md.mname = "init") c.methods in
  if c.methods = [] then begin
    emit "        if method == 'init': pass\n"
  end else begin
    List.iteri (fun i (md : method_decl) ->
      let kw = if i = 0 then "if" else "elif" in
      emitf "        %s method == %S: self.m_%s(sender_id, args)\n" kw md.mname md.mname
    ) c.methods;
    if not has_init then
      emit "        elif method == 'init': pass\n"
  end;
  emit "\n"

let gen_program_python ?(max_messages = 12) (p : program) : string =
  Buffer.clear buf;
  let cs = classes_of p in
  let gs = globals_of p in
  emit py_runtime_prelude;
  emit "\n";
  emitf "_max_messages = %d\n\n" max_messages;
  (* class definitions *)
  List.iter gen_class_py cs;
  (* global declarations *)
  List.iter (fun s ->
    match s.sdesc with
    | VarDecl (x, _) -> emitf "g_%s = None\n" x
    | _ -> ()
  ) gs;
  emit "\n";
  (* main *)
  emit "def main():\n";
  let global_names_l =
    List.filter_map (fun s ->
      match s.sdesc with VarDecl (x, _) -> Some x | _ -> None) gs
  in
  if global_names_l <> [] then
    emitf "    global %s\n"
      (String.concat ", " (List.map (fun x -> "g_" ^ x) global_names_l));
  let g_ctx = { cname = ""; fields = []; params = []; locals = [] } in
  emit "    # phase 1: alloc all globals (no thread yet)\n";
  List.iter (fun s ->
    match s.sdesc with
    | VarDecl (x, { desc = New (cls, args); _ }) ->
        let xs = String.concat ", " (List.map (gen_expr_py ~ctx:g_ctx) args) in
        emitf "    g_%s = %s([%s]).id\n" x cls xs
    | VarDecl (x, e) ->
        emitf "    g_%s = %s\n" x (gen_expr_py ~ctx:g_ctx e)
    | _ -> ()
  ) gs;
  emit "    # phase 2: spawn all actor threads\n";
  emit "    with _objects_lock:\n";
  emit "        all_objs = list(_objects.values())\n";
  emit "    for o in all_objs:\n";
  emit "        o._spawn()\n";
  emit "    # phase 3: top-level Send / CallStmt in source order\n";
  List.iter (fun s ->
    match s.sdesc with
    | VarDecl _ -> ()
    | Send (tgt, meth, args) | UnsafeSend (tgt, meth, args) ->
        let rid = target_id_py ~ctx:g_ctx tgt in
        let xs = String.concat ", " (List.map (gen_expr_py ~ctx:g_ctx) args) in
        emitf "    _enqueue(-1, %s, %S, [%s])\n" rid meth xs
    | CallStmt ("print", [arg]) ->
        emitf "    _v_print(%s)\n" (gen_expr_py ~ctx:g_ctx arg)
    | CallStmt (f, args) ->
        let xs = String.concat ", " (List.map (gen_expr_py ~ctx:g_ctx) args) in
        emitf "    %s(%s)\n" (mangle f) xs
    | _ -> ()
  ) gs;
  emit "    # wait for shutdown\n";
  emit "    while not _global_shutdown:\n";
  emit "        time.sleep(0.05)\n";
  emit "    for o in all_objs:\n";
  emit "        if o._thread:\n";
  emit "            o._thread.join(timeout=0.5)\n";
  emit "    _v_print('[abcl] done; messages=' + str(_messages_processed))\n";
  emit "\n";
  emit "if __name__ == '__main__':\n";
  emit "    main()\n";
  Buffer.contents buf
