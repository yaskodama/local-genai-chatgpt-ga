open Ast
open Thread
open Mutex
open Sdl_helper

type message = stmt_desc

type value =
  | VInt of int
  | VFloat of float
  | VString of string
  | VBool of bool
  | VUnit
  | VActor of string * (string, value) Hashtbl.t
  | VArray of value array * Types.ty option

type mmessage = {
  from : string;
  stmt : Ast.stmt;
  msg_id : string option;
}

type actor = {
  name : string;
  mutable cls  : string;
  queue : mmessage Queue.t;
  mutex : Mutex.t;
  cond  : Condition.t;
  env   : (string, value) Hashtbl.t;
  methods : (string, method_decl) Hashtbl.t;
  mutable last_sender : string;
}

let actor_table : (string, actor) Hashtbl.t = Hashtbl.create 32

(* sid -> (id counter, (id * line) list) *)
let sid_log_mu = Mutex.create ()
let sid_log_next : (string, int ref) Hashtbl.t = Hashtbl.create 64
let sid_logs : (string, (int * string) list ref) Hashtbl.t = Hashtbl.create 64
let sid_log_limit = 500

(* current message id while executing a message (for reply correlation) *)
let current_msg_id : string option ref = ref None
let set_current_msg_id (id:string option) = current_msg_id := id
let get_current_msg_id () = !current_msg_id

(* current actor name while executing a message (for session log) *)
let current_actor_name : string option ref = ref None
let set_current_actor_name (nm:string option) = current_actor_name := nm
let get_current_actor_name () = !current_actor_name

(* ---------------- Web/Debug log buffer (per actor) ---------------- *)
type log_entry = int * string

type log_buf = {
  mutable next_id : int;
  q : log_entry Queue.t;
}

let log_capacity = 300

let actor_logs : (string, log_buf) Hashtbl.t = Hashtbl.create 64

let get_log_buf (actor_name:string) : log_buf =
  match Hashtbl.find_opt actor_logs actor_name with
  | Some b -> b
  | None ->
      let b = { next_id = 1; q = Queue.create () } in
      Hashtbl.add actor_logs actor_name b;
      b

let push_log (actor_name:string) (line:string) : unit =
  let b = get_log_buf actor_name in
  let id = b.next_id in
  b.next_id <- b.next_id + 1;
  Queue.add (id, line) b.q;
  while Queue.length b.q > log_capacity do
    ignore (Queue.take b.q)
  done

let get_logs_since (actor_name:string) (after_id:int) : int * string list =
  let b = get_log_buf actor_name in
  let acc = ref [] in
  Queue.iter (fun (id, s) -> if id > after_id then acc := s :: !acc) b.q;
  (b.next_id, List.rev !acc)

let env : (string, value) Hashtbl.t = Hashtbl.create 64

let push_sid_log (sid:string) (line:string) =
  Mutex.lock sid_log_mu;
  let next =
    match Hashtbl.find_opt sid_log_next sid with
    | Some r -> r
    | None -> let r = ref 0 in Hashtbl.add sid_log_next sid r; r
  in
  let buf =
    match Hashtbl.find_opt sid_logs sid with
    | Some r -> r
    | None -> let r = ref [] in Hashtbl.add sid_logs sid r; r
  in
  let id = !next in
  incr next;
  buf := (id, line) :: !buf;
  (* keep newest *)
  let rec take n xs =
    if n <= 0 then [] else match xs with [] -> [] | x::tl -> x :: take (n-1) tl
  in
  buf := take sid_log_limit !buf;
  Mutex.unlock sid_log_mu

let get_sid_logs_since (sid:string) (after:int) : (int * string list) =
  Mutex.lock sid_log_mu;
  let buf =
    match Hashtbl.find_opt sid_logs sid with
    | Some r -> !r
    | None -> []
  in
  let newer = buf |> List.filter (fun (id,_) -> id > after) |> List.rev in
  let next =
    match buf with [] -> after | (id,_)::_ -> id
  in
  let lines = List.map snd newer in
  Mutex.unlock sid_log_mu;
  (next, lines)

let sid_of_actor_name (name:string) : string option =
  match String.split_on_char '_' name with
  | _base :: sid_parts when sid_parts <> [] ->
      Some (String.concat "_" sid_parts)
  | _ -> None

(* ===== web demo: print log ===== *)
let web_log_mutex = Mutex.create ()
let web_log_next_id = ref 0
let web_logs : (int * string) list ref = ref []

let web_log_limit = 500

let rec take n xs =
  if n <= 0 then []
  else match xs with
  | [] -> []
  | x::tl -> x :: take (n-1) tl

let push_web_log (s:string) =
  Mutex.lock web_log_mutex;
  let id = !web_log_next_id in
  incr web_log_next_id;
  web_logs := (id, s) :: !web_logs;
  if List.length !web_logs > web_log_limit then
    web_logs := List.rev (take web_log_limit (List.rev !web_logs));
  Mutex.unlock web_log_mutex

let get_web_logs_since (after:int) : (int * string list) =
  Mutex.lock web_log_mutex;
  let newer =
    !web_logs
    |> List.filter (fun (id,_) -> id > after)
    |> List.rev
  in
  let next =
    match !web_logs with
    | [] -> after
    | (id,_)::_ -> id
  in
  let lines = List.map snd newer in
  Mutex.unlock web_log_mutex;
  (next, lines)

(* ===== web demo: event log ===== *)
let web_evt_mutex = Mutex.create ()
let web_evt_next_id = ref 0
let web_evts : (int * string) list ref = ref []
let web_evt_limit = 500

let push_web_evt (s:string) =
  Mutex.lock web_evt_mutex;
  let id = !web_evt_next_id in
  incr web_evt_next_id;
  web_evts := (id, s) :: !web_evts;
  web_evts := take web_evt_limit !web_evts;
  Mutex.unlock web_evt_mutex

let get_web_evts_since (after:int) : (int * string list) =
  Mutex.lock web_evt_mutex;
  let newer = !web_evts |> List.filter (fun (id,_) -> id > after) |> List.rev in
  let next = match !web_evts with [] -> after | (id,_)::_ -> id in
  let lines = List.map snd newer in
  Mutex.unlock web_evt_mutex;
  (next, lines)

let debug_print_actor_table () =
  print_endline "[actor_table]";
  Hashtbl.iter
    (fun aname (a:actor) ->
      (* クラス名の取り出し：__class > self > a.cls の順でフォールバック *)
      let cls_name =
        match Hashtbl.find_opt a.env "__class" with
        | Some (VString cn) -> cn
        | _ ->
          (match Hashtbl.find_opt a.env "self" with
           | Some (VActor (cn, _)) -> cn
           | _ -> a.cls)
      in
      (* 型（メソッド表）を整形して表示 *)
      let methods = Types.lookup_class_methods_inst cls_name in
      let ty_str =
        if methods = [] then
          "actor(" ^ cls_name ^ ")"
        else
          (* string_of_ty_pretty が未導入なら string_of_ty に置換可 *)
          Types.string_of_ty_pretty (Types.TActor (cls_name, methods))
      in
      let mbox_len =
        try Queue.length a.queue with _ -> 0
      in
      let mnames =
        Hashtbl.to_seq_keys a.methods |> List.of_seq |> String.concat ", "
      in
      Printf.printf "- %s : %s\n    mbox: %d\n    methods: %s\n%!"
        aname ty_str mbox_len (if mnames = "" then "(none)" else mnames)
    )
    actor_table;
  flush stdout

(* actor_table を走査する汎用イテレータ *)
let iter_actor_table (k : string -> actor -> unit) : unit =
  Hashtbl.iter (fun aname a -> k aname a) actor_table

(* メールボックス長（非同期メッセージキューの長さ） *)
let mailbox_len (a:actor) : int =
  try Queue.length a.queue with _ -> 0

(* メソッド名一覧（定義順はハッシュ順） *)
let method_names (a:actor) : string list =
  Hashtbl.to_seq_keys a.methods |> List.of_seq

(* クラス名の取得（env の "__class" があれば優先、無ければ a.cls、最後に aname をフォールバック） *)
let actor_class_name (aname:string) (a:actor) : string =
  match Hashtbl.find_opt a.env "__class" with
  | Some (VString cn) -> cn
  | _ -> (try a.cls with _ -> aname)

(* Public helper: look up an actor's class name by actor name. *)
let lookup_actor_class (aname:string) : string option =
  match Hashtbl.find_opt actor_table aname with
  | None -> None
  | Some a -> Some (actor_class_name aname a)

let light_lookup_or_empty (cls : string) : (string * Types.ty) list =
  match Types.lookup_class_methods_inst cls with
  | ms -> ms
  (* もしあなたの実装が Hashtbl.find を直接返していて Not_found 例外を投げる場合はこちらを使ってください:
  | exception Not_found -> [] *)


(* === ObjectStore: 再代入で上書きされる「前の値」を保管しておくための簡易仕組み === *)

let iter_active_actors (k : string -> string -> unit) : unit =
  Hashtbl.iter
    (fun aname (a : actor) ->
       let cls_name =
         match Hashtbl.find_opt a.env "__class" with
         | Some (VString cn) -> cn
         | _ ->
           (match Hashtbl.find_opt a.env "self" with
            | Some (VActor (cn, _)) -> cn
            | _ -> aname)  (* フォールバック：不明なら名前 *)
       in
       k aname cls_name)
    actor_table

(* 値を保存するテーブル（id -> value） *)
let object_store : (int, value) Hashtbl.t = Hashtbl.create 256

(* 採番用のカウンタ *)
let object_store_index = ref 0

(* 変数ごとの履歴（key -> id list）。key は "<global>.x" や "ActorName.x" など *)
let var_history : (string, int list) Hashtbl.t = Hashtbl.create 128

(* 値を保存して採番 id を返す *)
let store_value (v:value) : int =
  incr object_store_index;
  Hashtbl.replace object_store !object_store_index v;
  !object_store_index

(* key で履歴を持たせる。戻り値は保存された id *)
let remember (key:string) (v:value) : int =
  let id = store_value v in
  let ids = match Hashtbl.find_opt var_history key with Some xs -> xs | None -> [] in
  Hashtbl.replace var_history key (id :: ids);
  id

let get_stored (id:int) : value option = Hashtbl.find_opt object_store id
let get_history (key:string) : int list =
  match Hashtbl.find_opt var_history key with Some xs -> xs | None -> []

let instance_source : (string, class_decl) Hashtbl.t = Hashtbl.create 64

let register_instance_source (instance_name : string) (src : class_decl) : unit =
  Hashtbl.replace instance_source instance_name src

let get_instance_source (instance_name : string) : class_decl option =
  Hashtbl.find_opt instance_source instance_name

let class_env : (string, class_decl) Hashtbl.t = Hashtbl.create 64

let register_class (c:class_decl) =
  Hashtbl.replace class_env c.cname c

let find_class_exn (name:string) : class_decl =
  match Hashtbl.find_opt class_env name with
  | Some c -> c
  | None -> failwith ("Class not found: " ^ name)

(* ===== debug switches ===== *)
let debug_send      = ref true
let debug_dispatch  = ref true
let debug_resolve   = ref true
let debug_mailbox   = ref true

(* 値の表示（未対応の値は <value> とする） *)
let rec string_of_value v =
  match v with
  | VInt n    -> string_of_int n
  | VFloat f  -> string_of_float f
  | VString s -> s
  | VBool b   -> string_of_bool b
  | VUnit     -> "()"
  | VActor (n,_) -> "<actor:" ^ n ^ ">"
  | VArray (a,_) ->
      let items =
        a |> Array.to_list |> List.map string_of_value |> String.concat ", "
      in
      "[" ^ items ^ "]"

let pp_recv = function
  | Var id -> id
  | _      -> "<expr>"

let type_name_of_value = function
  | VInt _ -> "int"
  | VFloat _  -> "float"
  | VString _ -> "string"
  | VBool _   -> "bool"
  | VUnit     -> "unit"
  | VActor _  -> "actor"
  | VArray _  -> "array"

let lookup_opt (env : (string, 'a) Hashtbl.t) (k : string) : 'a option =
  Hashtbl.find_opt env k

let bind (env : (string, 'a) Hashtbl.t) (k : string) (v : 'a) : unit =
  Hashtbl.replace env k v

let mem  (env : (string, 'a) Hashtbl.t) (k : string) : bool =
  match lookup_opt env k with Some _ -> true | None -> false

let find_actor_exn name =
  try Hashtbl.find actor_table name with Not_found ->
    failwith ("send: unknown actor: " ^ name)

let get_var x =
  try Hashtbl.find env x
  with Not_found -> failwith ("unbound variable: " ^ x)

let set_var x v =
  (match Hashtbl.find_opt env x with
   | Some old -> ignore (remember ("<global>." ^ x) old)
   | None -> ());
  Hashtbl.replace env x v

let to_bool = function
  | VBool b -> b
  | VFloat f -> f <> 0.0
  | VString s -> failwith ("string is not allowed as condition: " ^ s)
  | VUnit -> false
  | VActor _   -> failwith "actor is not allowed as condition"
  | VArray (_,_)   -> failwith "array is not allowed as condition"
  | VInt i -> i <> 0

let as_bool = function
  | VBool b   -> b
  | VFloat f  -> f <> 0.0
  | VString s -> failwith ("string is not allowed as condition: " ^ s)
  | VUnit     -> false
  | VActor _  -> failwith "actor is not allowed as condition"
  | VArray (_,_)   -> failwith "array is not allowed as condition"
  | VInt i -> i <> 0

let as_float (v : value) : float =
  match v with
  | VFloat f -> f
  | VInt i   -> float_of_int i
  | _        -> failwith "number (int/float) expected"

let as_int (v : value) : int =
  match v with
  | VInt i   -> i
  | VFloat f -> int_of_float f
  | _        -> failwith "int expected"

let as_string = function
  | VString s -> s
  | v -> failwith (Printf.sprintf "expected string, got %s" (type_name_of_value v))

let to_string_plain = function
  | VString s -> s
  | VFloat f  -> string_of_float f
  | VInt n -> string_of_int n
  | VBool  b  -> if b then "true" else "false"
  | VUnit     -> "()"
  | VActor (n,_)  -> "<actor:" ^ n ^ ">"
  | VArray (a,_)   ->                           (* 追加：簡易表現でOK *)
      let items =
        a |> Array.to_list
          |> List.map (function
                | VString s -> s
                | VInt n    -> string_of_int n
                | VFloat f  -> string_of_float f
                | VBool b   -> if b then "true" else "false"
                | VUnit     -> "()"
                | VActor (n,_)  -> "<actor:" ^ n ^ ">"
                | VArray (_,_)  -> "<array>")
          |> String.concat ", "
      in
      "[" ^ items ^ "]"

(* 追加: 数値かどうか判定＆Floatに昇格するヘルパ *)
let is_number = function
  | VInt _ | VFloat _ -> true
  | _ -> false

let as_float_value = function
  | VFloat f -> f
  | VInt n   -> float_of_int n
  | v        -> failwith (Printf.sprintf "expected number, got %s" (type_name_of_value v))
      
let apply_binop op v1 v2 =
  match op, v1, v2 with
 (* --- 数値演算: Int/Float 混在を許可（Float に昇格） --- *)
  | ("+"|"-"|"*"|"/"), v1, v2 when is_number v1 && is_number v2 ->
      let a = as_float_value v1 and b = as_float_value v2 in
      VFloat (match op with
        | "+" -> a +. b | "-" -> a -. b
        | "*" -> a *. b | "/" -> a /. b
        | _ -> assert false)

  (* --- 比較演算: 数値同士は昇格して比較 --- *)
  | (">"|">="|"<"|"<="|"=="|"!="), v1, v2 when is_number v1 && is_number v2 ->
      let a = as_float_value v1 and b = as_float_value v2 in
      VBool (match op with
        | ">" -> a > b | ">=" -> a >= b
        | "<" -> a < b | "<=" -> a <= b
        | "==" -> a = b | "!=" -> a <> b
        | _ -> assert false)

  (* --- 文字列連結（片側が string ならもう片側を文字列化して連結） --- *)
  | "+", VString s1, VString s2 -> VString (s1 ^ s2)
  | "+", VString s1, v2         -> VString (s1 ^ to_string_plain v2)
  | "+", v1,         VString s2 -> VString (to_string_plain v1 ^ s2)
  (* --- 文字列等価 --- *)
  | "==", VString a, VString b -> VBool (a = b)
  | "!=", VString a, VString b -> VBool (a <> b)
  | _ ->
    failwith ("unsupported binop/operands: " ^ op)

let expr_of_value = function
  | VInt n    -> Int n            (* keep integers as Int, not String *)
  | VFloat f  -> Float f
  | VString s -> String s
  | VBool  b  -> String (if b then "true" else "false")  (* Bool/Unit の式型が無ければ文字列化でOK *)
  | VUnit     -> String "()"
  | VActor (n,_)  -> String ("<actor:" ^ n ^ ">")
  | VArray (a,_)  ->                                        (* 追加：簡易表示でOK *)
      let items =
        a |> Array.to_list
          |> List.map (function
                | VString s -> s
                | VInt n    -> string_of_int n
                | VFloat f  -> string_of_float f
                | VBool b   -> if b then "true" else "false"
                | VUnit     -> "()"
                | VActor (n,_)  -> "<actor:" ^ n ^ ">"
                | VArray (_,_)  -> "<array>")
          |> String.concat ", "
      in
      String ("[" ^ items ^ "]")
      
(* === Value extractors === *)
let get_var_a (actor:actor) (x:string) : value =
  match Hashtbl.find_opt actor.env x with
  | Some v -> v
  | None   -> failwith ("unbound variable: " ^ x)

let set_var_a (actor:actor) (x:string) (v:value) : unit =
  (match Hashtbl.find_opt actor.env x with
   | Some old -> ignore (remember (actor.name ^ "." ^ x) old)
   | None -> ());
  (* その後で通常通りに上書き *)
  Hashtbl.replace actor.env x v

let create_actor name cls =
  {
    name;
    cls;
    queue = Queue.create ();
    mutex = Mutex.create ();
    cond = Condition.create ();
    env = Hashtbl.create 32;
    methods = Hashtbl.create 32;
    last_sender = "";
  }

let send_message ?msg_id ~from (target_name:string) (stmt:Ast.stmt) : unit = (
(*  let log_message () = (
    let oc = open_out_gen [Open_creat; Open_append; Open_text] 0o644 "message_log.txt" in
    Printf.fprintf oc "[SEND] to %s: %s\n" target_name
      (match msg with CallStmt(m,_) -> m | _ -> "stmt");
    close_out oc
  in *)
(*  log_message (); *)
  match Hashtbl.find_opt actor_table target_name with
  | Some actor ->
      let m = { msg_id; from; stmt } in
      Mutex.lock actor.mutex;
      (* Do NOT set actor.last_sender here — it is now set in actor_loop
         when the message is dequeued, so concurrent senders don't clobber
         each other's sender identity. *)
      Queue.push m actor.queue;
      Condition.signal actor.cond;
      Mutex.unlock actor.mutex
  | None ->
      Printf.printf "Actor %s not found\n" target_name
)

let prim_typeof =
  ("typeof", function
     | [VInt _] -> VString "int"
     | [VFloat _]  -> VString "float"
     | [VString _] -> VString "string"
     | [VBool _]   -> VString "bool"
     | [VUnit]     -> VString "unit"
     | [VActor (cls_name, _)] ->
       let methods = Types.lookup_class_methods_inst cls_name in
         if methods = [] then VString ("actor(" ^ cls_name ^ ")")
         else VString (Types.string_of_ty_pretty (TActor (cls_name, methods)))
     | [VArray (_, Some ty)] ->
       let s = Types.string_of_ty_pretty ty in
	VString (s^"[]")
     | [VArray (_, None)] -> VString "array"
     | _ -> failwith "typeof: expected exactly one argument")

(* ---- Helpers for array prims ---- *)
let expect_array (v:value) =
  match v with
  | VArray (a,_) -> a
  | _ -> failwith "array_*: not an array"

let expect_index (v:value) =
  match v with
  | VInt i -> i
  | VFloat f -> int_of_float f     (* float しかリテラルが無い場合の救済 *)
  | _ -> failwith "array_*: index must be int/float"

let make_array (a:value array) = VArray (a,None)

(* ===== 5) 組み込み関数 ===== *)
let prim1_float_float name f = (name, function
  | [VFloat x] -> VFloat (f x)
  | _ -> failwith (name ^ ": expected (float)"))

let prim1_print =
  ("print", function
     | [v] ->
         let s =
           match v with
           | VInt i -> string_of_int i
           | VString s -> s
           | VFloat f -> string_of_float f
           | VBool b -> if b then "true" else "false"
           | VUnit -> "()"
           | _ -> failwith "print: expected (string|float|bool|unit)"
         in
         print_endline s;

         (* ★ 既存のグローバル log にも積んでいるならここで push_web_log s を呼ぶ *)
         (* push_web_log s; *)

         (* ★ sid別ログに積む *)
         (match get_current_actor_name () with
          | None -> ()
          | Some aname ->
              (match sid_of_actor_name aname with
               | None -> ()
               | Some sid -> push_sid_log sid s));
         VUnit
     | _ -> failwith "print: arity 1 expected")

(* let prim1_print =
  ("print", function
     | [VInt i] -> print_endline (string_of_int i); VUnit
     | [VString s] -> print_endline s; VUnit
     | [VFloat  f] -> print_endline (string_of_float f); VUnit
     | [VBool   b] -> print_endline (if b then "true" else "false"); VUnit
     | [VUnit]     -> print_endline "()"; VUnit
     | _ -> failwith "print: expected (string|float|bool|unit)")
*)

let prim_wait =
  ("wait",
   function
   | [VFloat f] ->
       Thread.delay (f /. 1000.0);  (* ミリ秒 → 秒に換算 *)
       VUnit
   | [VString s] ->
       let f = float_of_string s in
       Thread.delay (f /. 1000.0);
       VUnit
   | _ -> failwith "wait: expected one float (ms)")

let sid_of_actor_name (name:string) : string option =
  (* "calc_<sid>" 形式を想定。最初の '_' 以降を sid とみなす *)
  match String.index_opt name '_' with
  | None -> None
  | Some i ->
      if i + 1 >= String.length name then None
      else Some (String.sub name (i+1) (String.length name - i - 1))

let rec take n xs =
  if n <= 0 then []
  else match xs with [] -> [] | x::tl -> x :: take (n-1) tl

let sid_log_mu = Mutex.create ()
let sid_log_next : (string, int ref) Hashtbl.t = Hashtbl.create 64
let sid_logs : (string, (int * string) list ref) Hashtbl.t = Hashtbl.create 64
let sid_log_limit = 500

let push_sid_log (sid:string) (line:string) : unit =
  Mutex.lock sid_log_mu;
  let next =
    match Hashtbl.find_opt sid_log_next sid with
    | Some r -> r
    | None -> let r = ref 0 in Hashtbl.add sid_log_next sid r; r
 in
 let buf =
    match Hashtbl.find_opt sid_logs sid with
    | Some r -> r
    | None -> let r = ref [] in Hashtbl.add sid_logs sid r; r
  in
  let id = !next in
  incr next;
  buf := (id, line) :: !buf;
  buf := take sid_log_limit !buf;
  Mutex.unlock sid_log_mu

let get_sid_logs_since (sid:string) (after:int) : (int * string list) =
  Mutex.lock sid_log_mu;
  let buf =
    match Hashtbl.find_opt sid_logs sid with
    | Some r -> !r
    | None -> []
  in
  let newer = buf |> List.filter (fun (id,_) -> id > after) |> List.rev in
  let next = match buf with [] -> after | (id,_)::_ -> id in
  let lines = List.map snd newer in
  Mutex.unlock sid_log_mu;
  (next, lines)

(* 値から対応する型を推定する関数 *)
let rec type_of_value = function
  | VInt _ -> Types.TInt
  | VFloat _ -> Types.TFloat
  | VBool _ -> Types.TBool
  | VString _ -> Types.TString
  | VArray (_, Some t) -> Types.TArray t
  | VArray (_, None) -> Types.TArray Types.TUnit
  | VUnit -> Types.TUnit
  | _ -> Types.TUnit

let prim_table : (string, value list -> value) Hashtbl.t =
  let h = Hashtbl.create 32 in
  let add (n,f) = Hashtbl.replace h n f in
  List.iter add [
    prim1_float_float "sin" sin;
    prim1_float_float "cos" cos;
    prim1_float_float "tan" tan;
    prim1_float_float "asin" asin;
    prim1_float_float "acos" acos;
    prim1_float_float "atan" atan;
    prim1_float_float "sqrt" sqrt;
    prim1_float_float "exp" exp;
    prim1_float_float "log10" (fun x -> log10 x);
    prim1_float_float "abs" abs_float;
    prim1_float_float "floor" (fun x -> floor x);
    prim1_float_float "ceil" (fun x -> ceil x);
    prim1_float_float "round" (fun x -> Float.round x);
    prim1_print;
    prim_typeof;
    prim_wait;
    ("wait",
      (function
        | [v] ->
            let ms = as_float v in
            let sec = ms /. 1000.0 in
            Thread.delay sec;
            VUnit
        | _ -> failwith "wait(ms): arity 1 expected"));
    ("sdl_init",
      (function
        | [VInt w; VInt h] ->
            Sdl_helper.sdl_init ~w ~h ~title:"ABCL/c+"; VUnit
        | [VFloat wf; VFloat hf] ->
            Sdl_helper.sdl_init ~w:(int_of_float wf) ~h:(int_of_float hf) ~title:"ABCL/c+"; VUnit
        | [VInt w; VFloat hf] ->
            Sdl_helper.sdl_init ~w ~h:(int_of_float hf) ~title:"ABCL/c+"; VUnit
        | [VFloat wf; VInt h] ->
            Sdl_helper.sdl_init ~w:(int_of_float wf) ~h ~title:"ABCL/c+"; VUnit
        | _ -> failwith "sdl_init(width:int|float, height:int|float): arity 2 expected"));
    ("sdl_clear",
      (function
        | [] -> Sdl_helper.sdl_clear (); VInt 0
        | _  -> failwith "sdl_clear(): arity 0 expected"));
    ("sdl_present",
      (function
        | [] -> Sdl_helper.sdl_present (); VInt 0
        | _  -> failwith "sdl_present(): arity 0 expected"));
    ("sdl_line",
      (function
        | [x1; y1; x2; y2] ->
            let x1 = as_int x1 and y1 = as_int y1 and x2 = as_int x2 and y2 = as_int y2 in
		Sdl_helper.sdl_draw_line x1 y1 x2 y2; VInt 0
        | _ -> failwith "sdl_line(x1,y1,x2,y2): arity 4 expected"));
    ("sdl_erase_line",
      (function
        | [x1; y1; x2; y2] ->
            let x1 = as_int x1 and y1 = as_int y1 and x2 = as_int x2 and y2 = as_int y2 in
                Sdl_helper.sdl_erase_line x1 y1 x2 y2; VInt 0
        | _ -> failwith "sdl_erase_line(x1,y1,x2,y2): arity 4 expected"));
    ("sdl_line_c",
      (function
        | [x1; y1; x2; y2; r; g; b] ->
            let x1 = as_int x1 and y1 = as_int y1
            and x2 = as_int x2 and y2 = as_int y2
            and r  = as_int r  and g  = as_int g  and b = as_int b in
            Sdl_helper.sdl_draw_line_rgb x1 y1 x2 y2 r g b; VInt 0
        | _ -> failwith "sdl_line_c(x1,y1,x2,y2,r,g,b): arity 7 expected"));
    ("array_empty",
      (function
        | [] -> VArray ([||], None)
        | _  -> failwith "array_empty(): arity 0 expected"));
    ("array_len",
      (function
        | [VArray (a,_)] -> VInt (Array.length a)
        | [_]        -> failwith "array_len(xs): xs must be array"
        | _          -> failwith "array_len(xs): arity 1 expected"));
    ("array_get",
      (function
        | [VArray (a,_); VInt i] ->
            if 0 <= i && i < Array.length a then a.(i)
            else failwith "array_get: index out of bounds"
        | [VArray (a,_); VFloat f] ->
            let i = int_of_float f in
            if 0 <= i && i < Array.length a then a.(i)
            else failwith "array_get: index out of bounds"
        | [_; _]     -> failwith "array_get(xs,i): xs must be array and i must be int/float"
        | _          -> failwith "array_get(xs,i): arity 2 expected"));
    ("array_set",
      (function
        | [VArray (a,ty); VInt i; v] ->
            if 0 <= i && i < Array.length a then
              let b = Array.copy a in b.(i) <- v;
	      let elem_ty =
  	        match ty with
	        | Some _ -> ty
                | None -> Some(type_of_value v)
	      in
	        VArray (b,elem_ty)
            else failwith "array_set: index out of bounds"
        | [VArray (a,ty); VFloat f; v] ->
            let i = int_of_float f in
            if 0 <= i && i < Array.length a then
              let b = Array.copy a in b.(i) <- v;
	      let elem_ty =
  	        match ty with
	        | Some _ -> ty
                | None -> Some(type_of_value v)
	      in
	        VArray (b,elem_ty)
            else failwith "array_set: index out of bounds"
        | [_; _; _]  -> failwith "array_set(xs,i,v): xs must be array and i must be int/float"
        | _          -> failwith "array_set(xs,i,v): arity 3 expected"));
    ("array_push",
      (function
	| [VArray(a,ty); v] ->
	  let elem_ty =
  	    match ty with
	    | Some _ -> ty
            | None -> Some(type_of_value v)
	  in
  	    VArray (Array.append a [| v |],elem_ty)
        | _ -> failwith "array_push(xs,v): arity 2 expected"));
    ("print",
      (function
        | [v] ->
        let s = string_of_value v in
	  print_endline s;
	  push_web_log s;
          VUnit
        | _ -> failwith "print(s): arity 1 expected"));
    ("actor_dump",
     (function
       | [VActor (cls_name, _)] ->
         let ms = Types.lookup_class_methods_inst cls_name in
         let s =
           if ms = [] then ("actor(" ^ cls_name ^ ")")
           else Types.string_of_ty_pretty (TActor (cls_name, ms))
         in
           print_endline s; VUnit
       | [v] ->
         print_endline ("(not an actor) typeof=" ^
           (match v with
            | VString _ -> "string" | VInt _ -> "int" | VFloat _ -> "float"
            | VBool _ -> "bool" | VArray _ -> "array" | VUnit -> "unit"
            | VActor (c,_) -> "actor("^c^")"));
           VUnit
       | _ -> failwith "actor_dump(x): arity 1 expected"));
  ];
  h

let call_prim name args =
  match Hashtbl.find_opt prim_table name with
  | Some f -> f args
  | None ->
(*      print_endline "[debug] prim_table keys:";
      Hashtbl.iter (fun k _ -> print_endline ("  - " ^ k)) prim_table; *)
      failwith ("Unknown function: " ^ name)

let add_prim name fn = Hashtbl.replace prim_table name fn

let find_actor_exn name =
  try Hashtbl.find actor_table name
  with Not_found -> failwith ("send: unknown actor: " ^ name)

let rec eval_expr (actor:actor) (e : expr) =
  match e.desc with
  | Int i -> VInt i
  | Float f  -> VFloat f
  | String s -> VString s
  | Var x    -> get_var_a actor x
  | Binop (op, e1, e2) ->
      let v1 = eval_expr actor e1 in
      let v2 = eval_expr actor e2 in
      apply_binop op v1 v2
  | Call (fname, arg1) ->
      let vs = List.map (eval_expr actor) arg1 in
      (* Make print observable from Web UI by recording it per actor. *)
      if fname = "print" then (
        match vs with
        | [v] ->
            let line = string_of_value v in
            push_log actor.name line;
            print_endline line;
            VUnit
        | _ -> failwith "print(s): arity 1 expected"
      ) else
        call_prim fname vs
  | Expr e -> eval_expr actor e
  | New (_cls, _args) ->
      failwith "eval_expr: New is not supported here"
  | Array (_es, _tyopt) ->
      failwith "eval_expr: Array is not supported here"
and eval_stmt (actor:actor) (s : Ast.stmt) =
  match s.sdesc with
  | Assign (x, e) -> set_var_a actor x (eval_expr actor e)
  | VarDecl (name, rhs) -> (
    match rhs.desc with
    | New (cls, args) -> (
    let cobj = find_class_exn cls in
      register_instance_source name cobj;
      let obj  = { cobj with cname = cls } in
      let actor_inst = create_actor obj.cname cls in
        List.iter
        (fun (st:Ast.stmt) ->
          match st.sdesc with
        | VarDecl (k, init) ->
          let v = eval_expr actor_inst init in
            Hashtbl.replace actor_inst.env k v
        | _ -> ()
        ) obj.fields;
        List.iter (fun (m:method_decl) ->
          Hashtbl.replace actor_inst.methods m.mname m
        ) obj.methods;
        Hashtbl.add actor_table name actor_inst;
        ignore (Thread.create (fun () -> actor_loop actor_inst) ());
        let init_opt = List.find_opt (fun (m:Ast.method_decl) -> m.mname = "init") obj.methods in
          (match init_opt with
          | None ->
            Printf.printf "[Actor] %s: no init; skipped\n%!" name;
            ()
          | Some m ->
            let need = List.length m.params and got  = List.length args in
              if need <> got then
                Printf.printf "[Actor] %s.init arity mismatch: expected %d but %d given — skipped\n%!"
                  name need got
              else
                send_message ~from:"<new>" name (mk_stmt (CallStmt("init", args))))
          );
          set_var_a actor name (VActor (cls, Hashtbl.create 0))
    | _ -> set_var_a actor name (eval_expr actor rhs))
  | If (cond, tbr, fbr) ->
      if to_bool (eval_expr actor cond)
      then eval_stmt actor tbr
      else eval_stmt actor fbr
  | While (cond, body) ->
      while to_bool (eval_expr actor cond) do
        eval_stmt actor body
      done
  | Become (new_cls, args) ->
      (* Change this actor's behavior (method table) to class new_cls.
         State (env) is preserved; missing fields are initialized from the new class. *)
      let cobj = find_class_exn new_cls in

      (* 1) class名を更新 *)
      actor.cls <- new_cls;
      Hashtbl.replace actor.env "__class" (VString new_cls);
      Hashtbl.replace actor.env "self" (VActor (new_cls, Hashtbl.create 0));

      (* 2) methods を差し替え *)
      Hashtbl.reset actor.methods;
      List.iter (fun (m:method_decl) ->
        Hashtbl.replace actor.methods m.mname m
      ) cobj.methods;

     (* 3) 新クラスの fields を「未定義のものだけ」初期化 *)
      List.iter (fun (st:Ast.stmt) ->
        match st.sdesc with
        | VarDecl (k, init) when not (Hashtbl.mem actor.env k) ->
            let v = eval_expr actor init in
            Hashtbl.replace actor.env k v
        | _ -> ()
      ) cobj.fields;

      (* 4) init(args) があれば同期で実行 *)
      if Hashtbl.mem actor.methods "init" then
        eval_stmt actor (mk_stmt (CallStmt ("init", args)))
      else
        ();
  | Seq ss ->
      List.iter (eval_stmt actor) ss
  | CallStmt ("sdl_init", [w; h]) ->
      let w = int_of_float (as_float (eval_expr actor w))
      and h = int_of_float (as_float (eval_expr actor h)) in
      Sdl_helper.sdl_init ~w ~h ~title:"ABCL/c+"
  | CallStmt ("sdl_clear", []) ->
      Sdl_helper.sdl_clear ()
  | CallStmt ("sdl_line", [x1; y1; x2; y2]) ->
      let x1 = int_of_float (as_float (eval_expr actor x1))
      and y1 = int_of_float (as_float (eval_expr actor y1))
      and x2 = int_of_float (as_float (eval_expr actor x2))
      and y2 = int_of_float (as_float (eval_expr actor y2)) in
      Sdl_helper.sdl_draw_line x1 y1 x2 y2
  | CallStmt ("sdl_present", []) ->
      Sdl_helper.sdl_present ()
  | CallStmt ("sdl_erase_line", [e1; e2; e3; e4]) ->
      let x1 = int_of_float (as_float (eval_expr actor e1))
      and y1 = int_of_float (as_float (eval_expr actor e2))
      and x2 = int_of_float (as_float (eval_expr actor e3))
      and y2 = int_of_float (as_float (eval_expr actor e4)) in
      Sdl_helper.sdl_erase_line x1 y1 x2 y2
  | CallStmt (mname, args) ->
    begin match Hashtbl.find_opt actor.methods mname with
    | Some mdecl ->
        let arg_vals = List.map (eval_expr actor) args in
        let params   = mdecl.params in
          if List.length params <> List.length arg_vals then
            Printf.printf "[%s] arity mismatch: %s expects %d but %d given\n%!"
            actor.name mname (List.length params) (List.length arg_vals);
        let saved = List.map (fun p -> (p, Hashtbl.find_opt actor.env p)) params in
          List.iter2 (fun p v -> Hashtbl.replace actor.env p v) params arg_vals;
          Hashtbl.replace actor.env "self" (VActor (actor.cls, Hashtbl.create 0));
          Hashtbl.replace actor.env "__class" (VString actor.cls);
          (* Expose `sender` as a plain string so == / != against "" works *)
          Hashtbl.replace actor.env "sender" (VString actor.last_sender);
          Hashtbl.replace actor.env "self"   (VString actor.name);
            eval_stmt actor mdecl.body;
            List.iter (fun (p, ov) ->
              match ov with Some v -> Hashtbl.replace actor.env p v | None -> Hashtbl.remove actor.env p
          ) saved
    | None ->
      let vs = List.map (eval_expr actor) args in
        ignore (call_prim mname vs)
    end
  | Send (target, meth, args) ->
    let arg_vals = List.map (eval_expr actor) args in
    let arg_exprs = List.map (fun v -> mk_expr (expr_of_value v)) arg_vals in
    begin match target with
    | LocalTarget tgt ->
        let actual_target =
          if tgt = "self" then actor.name
          else if tgt = "sender" then actor.last_sender
          else
            (* If tgt is a local variable holding an actor name, resolve it *)
            (match Hashtbl.find_opt actor.env tgt with
             | Some (VString s) when s <> "" -> s
             | Some (VActor (n, _)) -> n
             | _ -> tgt)
        in
        send_message ~from:actor.name actual_target
          (mk_stmt (CallStmt (meth, arg_exprs)))

    | RemoteTarget (hostport, tgt) ->
        Remote_client.remote_send
          ~hostport
          ~to_actor:tgt
          ~meth
          ~args:arg_exprs
          ~from:actor.name
    end
  | UnsafeSend (target, meth, args) ->
    let arg_vals = List.map (eval_expr actor) args in
    let arg_exprs = List.map (fun v -> mk_expr (expr_of_value v)) arg_vals in
    begin match target with
    | LocalTarget tgt ->
        let actual_target =
          if tgt = "self" then actor.name
          else if tgt = "sender" then actor.last_sender
          else
            (match Hashtbl.find_opt actor.env tgt with
             | Some (VString s) when s <> "" -> s
             | Some (VActor (n, _)) -> n
             | _ -> tgt)
        in
        send_message ~from:actor.name actual_target
          (mk_stmt (CallStmt (meth, arg_exprs)))
    | RemoteTarget (hostport, tgt) ->
        Remote_client.remote_send
          ~hostport
          ~to_actor:tgt
          ~meth
          ~args:arg_exprs
          ~from:actor.name
    end
  | Select (cases, (to_ms_opt, to_body_opt)) ->
    let start = Unix.gettimeofday () in
    let rec loop () =
      Mutex.lock actor.mutex;
      let picked = pop_matching_message actor cases in
      Mutex.unlock actor.mutex;
      match picked with
      | Some (m, binds, body_stmt) ->
          (* preserve your existing reply/msg_id correlation *)
          set_current_actor_name (Some actor.name);
          set_current_msg_id m.msg_id;

          (* bind variables into actor.env *)
          List.iter (fun (x,v) -> Hashtbl.replace actor.env x v) binds;

          (try eval_stmt actor body_stmt with _ -> ());
          set_current_msg_id None;
          set_current_actor_name None
      | None ->
          (* no match *)
          (match to_ms_opt, to_body_opt with
           | Some ms, Some to_stmt ->
               let elapsed_ms = (Unix.gettimeofday () -. start) *. 1000.0 in
               if elapsed_ms >= float_of_int ms then
                 (try eval_stmt actor to_stmt with _ -> ())
               else (Thread.delay 0.01; loop ())
           | _ ->
               (* wait until at least one message arrives *)
               Mutex.lock actor.mutex;
               while Queue.is_empty actor.queue do
                 Condition.wait actor.cond actor.mutex
               done;
               Mutex.unlock actor.mutex;
               loop ())
    in
    loop ()
and actor_loop actor = (
  while true do
    Mutex.lock actor.mutex;
    while Queue.is_empty actor.queue do
      Condition.wait actor.cond actor.mutex
    done;
    let msg = Queue.pop actor.queue in
    Mutex.unlock actor.mutex;
    (* Bind sender identity from the dequeued message, not a pre-set field.
       This makes `sender` correct even when multiple actors enqueue
       messages to this actor concurrently. *)
    actor.last_sender <- msg.from;
    set_current_actor_name (Some actor.name);
    set_current_msg_id msg.msg_id;
    (try
      eval_stmt actor msg.stmt
      with exn ->
      (* show runtime errors instead of swallowing them *)
        let id =
          match msg.msg_id with
          | Some s -> s
          | None -> "<no-id>"
        in
          Printf.eprintf "[FAILED] actor=%s msg_id=%s reason=%s\n%!"
            actor.name id (Printexc.to_string exn);
          push_web_evt (Printf.sprintf "[FAILED] id=%s to=%s reason=runtime:%s"
            id actor.name (Printexc.to_string exn))
    );
    set_current_msg_id None;
    set_current_actor_name None;
    done)
and resolve_actor_from_term env recv_term =
  match recv_term with
  | Var id ->
      (match lookup_opt env id with
       | Some (VActor (name,_)) -> find_actor_exn name
       | _                  -> find_actor_exn id)

  | _ ->
      let self_name =
        match lookup_opt env "self" with
        | Some (VActor (name,_)) -> name
        | _ -> failwith "send: receiver expression requires self; use a name or bind self"
      in
      let self_actor = find_actor_exn self_name in
      match eval_expr self_actor (mk_expr recv_term) with
      | VActor (name,_) -> find_actor_exn name
      | _ -> failwith "send: receiver expr must evaluate to an actor (VActor name)"
and match_callstmt actor (meth:string) (vars:string list) (m:mmessage)
  : (string * value) list option =
  match m.stmt.sdesc with
  | CallStmt (mname, arg_exprs) when mname = meth ->
      if List.length arg_exprs <> List.length vars then None
      else
        let vals = List.map (eval_expr actor) arg_exprs in
        Some (List.combine vars vals)
  | _ -> None
and pop_matching_message actor (cases:select_case list)
  : (mmessage * (string * value) list * stmt) option =
  (* actor.mutex is expected to be locked by caller *)
  let msgs = ref [] in
  while not (Queue.is_empty actor.queue) do
    msgs := Queue.pop actor.queue :: !msgs
  done;
  let msgs = List.rev !msgs in
  let rec scan acc = function
    | [] ->
        List.iter (fun mm -> Queue.push mm actor.queue) (List.rev acc);
        None
    | m :: rest ->
        let rec try_cases = function
          | [] -> None
          | c :: cs ->
              match match_callstmt actor c.pat.meth c.pat.vars m with
              | Some binds -> Some (binds, c.body)
              | None -> try_cases cs
        in
        match try_cases cases with
        | Some (binds, body_stmt) ->
            List.iter (fun mm -> Queue.push mm actor.queue) (List.rev acc);
            List.iter (fun mm -> Queue.push mm actor.queue) rest;
            Some (m, binds, body_stmt)
        | None ->
            scan (m :: acc) rest
  in
  scan [] msgs
  
let actor_exists (name:string) : bool =
  Hashtbl.mem actor_table name

let spawn_actor ~(class_name:string) ~(actor_name:string) : unit =
  if actor_exists actor_name then ()
  else begin
    (* class_decl を class_env から取得 *)
    let obj : class_decl = find_class_exn class_name in

    (* actor生成 *)
    let a = create_actor actor_name class_name in

    (* ★必須：メソッド表をコピー *)
    List.iter (fun (m:method_decl) ->
      Hashtbl.replace a.methods m.mname m
    ) obj.methods;

    (* （任意）fields 初期化：必要なら後で追加。まずは methods だけで init/add を動かす *)
    (*
    List.iter (fun (st:Ast.stmt) ->
      match st.sdesc with
      | VarDecl (k, init) ->
          let v = eval_expr a init in
          Hashtbl.replace a.env k v
      | _ -> ()
    ) obj.fields;
    *)

    (* 登録・起動 *)
    Hashtbl.add actor_table actor_name a;
    ignore (Thread.create actor_loop a);

    (* init を送る *)
    send_message ~from:"<new>" actor_name (mk_stmt (CallStmt ("init", [])));
  end

(*
let spawn_actor ~(class_name:string) ~(actor_name:string) : unit =
  (* すでに存在するなら何もしない *)
  if actor_exists actor_name then ()
  else begin
    (* 1) actor レコードの生成：あなたの create_actor 相当を使う *)
    let a = create_actor actor_name class_name in
    (* 2) 登録 *)
    Hashtbl.add actor_table actor_name a;
    (* 3) スレッド開始 *)
    ignore (Thread.create actor_loop a);
    (* 4) init を送る（args が無い版） *)
    send_message ~from:"<new>" actor_name (mk_stmt (CallStmt ("init", [])));
end
*)

let wait_ms ms =
   let seconds = ms /. 1000.0 in
   ignore (Unix.select [] [] [] seconds)

let show_actor_env actor =
  Hashtbl.fold (fun key value acc ->
    acc ^ Printf.sprintf "   %s = %s\n" key (string_of_value(value))
  ) actor.env ""

(* ここまでで定義した debug_print_actor_table を Typing_env に登録 *)
let () =
  Typing_env.set_actor_table_printer debug_print_actor_table
