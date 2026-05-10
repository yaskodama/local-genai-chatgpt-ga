(* web_gateway.ml
   Minimal HTTP gateway embedded in the AIPL runtime.

   - No external OCaml web libraries.
  - Runs as a background thread.
   - Lets a web browser send messages to actors.

   Endpoints:
     GET  /              -> simple HTML UI
     POST /api/send      -> send to actor by name
         form fields: to=<actorName>&method=<m>&args=<a,b,c>&from=<who>
     POST /api/x/<key>   -> send to exposed endpoint
         form fields: method=<m>&args=<a,b,c>&from=<who>

   Notes:
     - This is a demo-quality server. For production, use a real HTTP stack.
     - We support both form-encoded and JSON payloads (a tiny JSON parser is included).
*)

open Unix

(* We only need Eval_thread.send_message and Ast constructors. *)
open Ast
open Types

(* ---- REPL command callback ---- *)
let repl_command_handler : (string -> string) option ref = ref None

let set_repl_command_handler (f:string -> string) = repl_command_handler := Some f

(* ---------- Public API ---------- *)

(* Exposed endpoints: "key" -> actor_name *)
let exposed : (string, string) Hashtbl.t = Hashtbl.create 32

let expose ~(key:string) ~(actor_name:string) : unit = Hashtbl.replace exposed key actor_name

let list_exposed () : (string * string) list = Hashtbl.to_seq exposed |> List.of_seq

(* A single running server per process (good enough for now). *)
let server_thread : Thread.t option ref = ref None

(* msg_id -> sid *)
let msgid_to_sid : (string, string) Hashtbl.t = Hashtbl.create 2048
let msgid_mu = Mutex.create ()

let bind_msgid_sid (msg_id:string) (sid:string) =
  Mutex.lock msgid_mu;
  Hashtbl.replace msgid_to_sid msg_id sid;
  Mutex.unlock msgid_mu

let lookup_sid (msg_id:string) : string option =
  Mutex.lock msgid_mu;
  let r = Hashtbl.find_opt msgid_to_sid msg_id in
  Mutex.unlock msgid_mu;
  r

(* ---- Reply slots for /api/json/call (synchronous remote-now) ---- *)

type reply_slot = {
  rs_mu     : Mutex.t;
  rs_cv     : Condition.t;
  mutable rs_value : string option;  (* JSON-encoded reply value *)
  mutable rs_done  : bool;
}

let reply_slots : (string, reply_slot) Hashtbl.t = Hashtbl.create 64
let reply_slots_mu = Mutex.create ()

let register_reply_slot (msg_id:string) : reply_slot =
  let s = {
    rs_mu = Mutex.create (); rs_cv = Condition.create ();
    rs_value = None; rs_done = false;
  } in
  Mutex.lock reply_slots_mu;
  Hashtbl.replace reply_slots msg_id s;
  Mutex.unlock reply_slots_mu;
  s

let unregister_reply_slot (msg_id:string) : unit =
  Mutex.lock reply_slots_mu;
  Hashtbl.remove reply_slots msg_id;
  Mutex.unlock reply_slots_mu

(* Returns true if a slot was registered and resolved (or already done). *)
let try_resolve_reply_slot (msg_id:string) (json_value:string) : bool =
  Mutex.lock reply_slots_mu;
  let s = Hashtbl.find_opt reply_slots msg_id in
  Mutex.unlock reply_slots_mu;
  match s with
  | None -> false
  | Some slot ->
      Mutex.lock slot.rs_mu;
      if not slot.rs_done then begin
        slot.rs_value <- Some json_value;
        slot.rs_done <- true;
        Condition.signal slot.rs_cv
      end;
      Mutex.unlock slot.rs_mu;
      true

(* OCaml 4.x has no Condition.timedwait; we poll every 10ms.  This
   is acceptable here because the timeout window is seconds. *)
let wait_reply_slot (slot:reply_slot) ~(timeout_s:float) : string option =
  let deadline = Unix.gettimeofday () +. timeout_s in
  let rec poll () =
    Mutex.lock slot.rs_mu;
    let d = slot.rs_done in
    Mutex.unlock slot.rs_mu;
    if d then ()
    else if Unix.gettimeofday () >= deadline then ()
    else (Thread.delay 0.01; poll ())
  in
  poll ();
  Mutex.lock slot.rs_mu;
  let v = slot.rs_value in
  Mutex.unlock slot.rs_mu;
  v

(* ---- HMAC-SHA256 over the request body, matched against the
        X-ABCL-Sig header.  Mirrors the Python sender's wire format
        and is gated on ABCL_REMOTE_SECRET.  Verification shells out
        to openssl so we don't pull in a new opam dep. ---- *)

let read_all_in (ic:in_channel) : string =
  let b = Buffer.create 256 in
  (try while true do Buffer.add_channel b ic 256 done
   with End_of_file -> ());
  Buffer.contents b

let strip_trailing_newline (s:string) : string =
  let n = String.length s in
  if n > 0 && s.[n - 1] = '\n' then String.sub s 0 (n - 1) else s

let hmac_sha256_hex ~(secret:string) ~(data:string) : string =
  let cmd = Printf.sprintf "openssl dgst -sha256 -hmac %s" (Filename.quote secret) in
  let (ic, oc) = Unix.open_process cmd in
  output_string oc data;
  close_out oc;
  let line = strip_trailing_newline (read_all_in ic) in
  let _ = Unix.close_process (ic, oc) in
  (* openssl prints either "(stdin)= <hex>" or just "<hex>"; take the
     last whitespace-separated token. *)
  match String.rindex_opt line ' ' with
  | Some i when i + 1 < String.length line ->
      String.sub line (i + 1) (String.length line - i - 1)
  | _ -> line

let constant_time_eq (a:string) (b:string) : bool =
  if String.length a <> String.length b then false
  else
    let r = ref 0 in
    for i = 0 to String.length a - 1 do
      r := !r lor (Char.code a.[i] lxor Char.code b.[i])
    done;
    !r = 0

(* None when the request is allowed; Some response when rejected. *)
let verify_hmac_or_reject ~(headers:(string,string) Hashtbl.t) ~(body:string)
    : (int * string * string) option =
  match Sys.getenv_opt "ABCL_REMOTE_SECRET" with
  | None -> None
  | Some "" -> None
  | Some secret ->
      let provided =
        match Hashtbl.find_opt headers "x-abcl-sig" with
        | Some s -> String.trim s
        | None -> ""
      in
      if provided = "" then
        Some (401, "text/plain; charset=utf-8", "missing X-ABCL-Sig")
      else
        let expected = hmac_sha256_hex ~secret ~data:body in
        if constant_time_eq provided expected then None
        else Some (401, "text/plain; charset=utf-8", "invalid X-ABCL-Sig")

(* ---- websocket clients per sid ---- *)
let ws_clients : (string, out_channel list ref) Hashtbl.t = Hashtbl.create 64
let ws_clients_mu = Mutex.create ()

let ws_add (sid:string) (oc:out_channel) : unit =
  Mutex.lock ws_clients_mu;
  let r =
    match Hashtbl.find_opt ws_clients sid with
    | Some r -> r
    | None -> let r = ref [] in Hashtbl.add ws_clients sid r; r
  in
  r := oc :: !r;
  Mutex.unlock ws_clients_mu

let ws_remove (sid:string) (oc:out_channel) : unit =
  Mutex.lock ws_clients_mu;
  (match Hashtbl.find_opt ws_clients sid with
   | Some r -> r := List.filter (fun x -> x != oc) !r
   | None -> ());
  Mutex.unlock ws_clients_mu

let ws_send_to_sid (sid:string) (f:out_channel -> unit) : unit =
  Mutex.lock ws_clients_mu;
  let targets =
    match Hashtbl.find_opt ws_clients sid with
    | Some r -> !r
    | None -> []
  in
  Mutex.unlock ws_clients_mu;
  List.iter (fun oc -> try f oc with _ -> ()) targets

let ws_sid_has_clients (sid:string) : bool =
  Mutex.lock ws_clients_mu;
  let n =
    match Hashtbl.find_opt ws_clients sid with
    | Some r -> List.length !r
    | None -> 0
  in
  Mutex.unlock ws_clients_mu;
  n > 0

(* ---------- WebSocket helpers (RFC6455) ---------- *)

let ws_guid = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

(* Minimal SHA1 implementation (pure OCaml) *)
let sha1 (s:string) : bytes =
  let open Int32 in
  let ( ++ ) = add in
  let ( ** ) = logxor in
  let ( &&& ) = logand in
  let ( ||| ) = logor in

  let rol x n = (shift_left x n) ||| (shift_right_logical x (32 - n)) in

  let ml = String.length s in
  let bit_len = Int64.mul (Int64.of_int ml) 8L in


  (* padding *)
  let pad_len =
    let r = (ml + 1) mod 64 in
    if r <= 56 then (56 - r) else (56 + (64 - r))
  in
  let total = ml + 1 + pad_len + 8 in
  let msg = Bytes.make total '\000' in
  Bytes.blit_string s 0 msg 0 ml;
  Bytes.set msg ml (Char.chr 0x80);
  (* write 64-bit length big-endian *)
  for i = 0 to 7 do
    let shift = 8 * (7 - i) in
    let b =
      Int64.(to_int (logand (shift_right bit_len shift) 0xFFL))
    in
    Bytes.set msg (total - 8 + i) (Char.chr b)
  done;

  let h0 = ref 0x67452301l
  and h1 = ref 0xEFCDAB89l
  and h2 = ref 0x98BADCFEl
  and h3 = ref 0x10325476l
  and h4 = ref 0xC3D2E1F0l in


  let w = Array.make 80 0l in

  let read_u32_be b off =
    let c i = Int32.of_int (Char.code (Bytes.get b (off+i))) in
    (shift_left (c 0) 24) |||
    (shift_left (c 1) 16) |||
    (shift_left (c 2) 8)  |||
    (c 3)
  in

  let blocks = total / 64 in
  for bi = 0 to blocks - 1 do
    let base = bi * 64 in
    for i = 0 to 15 do
      w.(i) <- read_u32_be msg (base + (i*4))
    done;
    for i = 16 to 79 do
      w.(i) <- rol (w.(i-3) ** w.(i-8) ** w.(i-14) ** w.(i-16)) 1
    done;

    let a = ref !h0
    and b = ref !h1
    and c = ref !h2
    and d = ref !h3
    and e = ref !h4 in


    for i = 0 to 79 do
      let f,k =
        if i <= 19 then (((!b &&& !c) ||| ((lognot !b) &&& !d)), 0x5A827999l)
        else if i <= 39 then ((!b ** !c ** !d), 0x6ED9EBA1l)
        else if i <= 59 then (((!b &&& !c) ||| (!b &&& !d) ||| (!c &&& !d)), 0x8F1BBCDCl)
        else ((!b ** !c ** !d), 0xCA62C1D6l)
      in
      let temp = (rol !a 5) ++ f ++ !e ++ k ++ w.(i) in
      e := !d;
      d := !c;
      c := rol !b 30;
      b := !a;
      a := temp;
    done;

    h0 := !h0 ++ !a;
    h1 := !h1 ++ !b;
    h2 := !h2 ++ !c;
    h3 := !h3 ++ !d;
    h4 := !h4 ++ !e;
  done;

let out = Bytes.create 20 in
  let write_u32_be v off =
    let byte i = Char.chr (Int32.to_int (Int32.logand (Int32.shift_right_logical v (8*(3-i))) 0xFFl)) in
    Bytes.set out (off+0) (byte 0);
    Bytes.set out (off+1) (byte 1);
    Bytes.set out (off+2) (byte 2);
    Bytes.set out (off+3) (byte 3)
  in
  write_u32_be !h0 0;
  write_u32_be !h1 4;
  write_u32_be !h2 8;
  write_u32_be !h3 12;
  write_u32_be !h4 16;
  out

let base64_encode_bytes (b:bytes) : string =
  let tbl = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/" in
  let n = Bytes.length b in
  let out = Buffer.create ((n+2)/3*4) in
  let get i = Char.code (Bytes.get b i) in
  let rec loop i =
    if i >= n then ()
    else
      let b0 = get i in
      let b1 = if i+1 < n then get (i+1) else 0 in
      let b2 = if i+2 < n then get (i+2) else 0 in
      let triple = (b0 lsl 16) lor (b1 lsl 8) lor b2 in
      let c0 = (triple lsr 18) land 0x3F
      and c1 = (triple lsr 12) land 0x3F
      and c2 = (triple lsr 6)  land 0x3F
      and c3 = triple land 0x3F in
      Buffer.add_char out tbl.[c0];
      Buffer.add_char out tbl.[c1];
      if i+1 < n then Buffer.add_char out tbl.[c2] else Buffer.add_char out '=';
      if i+2 < n then Buffer.add_char out tbl.[c3] else Buffer.add_char out '=';
      loop (i+3)
  in
  loop 0;
  Buffer.contents out

let ws_accept (sec_key:string) : string =
  sec_key ^ ws_guid |> sha1 |> base64_encode_bytes

(* Write a server->client TEXT frame. *)
let ws_send_text (oc:out_channel) (payload:string) : unit =
  let len = String.length payload in
  let b0 = 0x81 (* FIN=1, opcode=TEXT *) in
  output_char oc (Char.chr b0);
  if len < 126 then begin
    output_char oc (Char.chr len)
  end else if len < 65536 then begin
    output_char oc (Char.chr 126);
    output_char oc (Char.chr ((len lsr 8) land 0xFF));
    output_char oc (Char.chr (len land 0xFF));
  end else begin
    (* very large not needed for demo; send as 64-bit length *)
    output_char oc (Char.chr 127);
    for i = 7 downto 0 do
      output_char oc (Char.chr ((len lsr (8*i)) land 0xFF))
    done
  end;
  output_string oc payload;
  flush oc

(* ---------- Tiny helpers ---------- *)

let is_space = function ' ' | '\t' | '\r' | '\n' -> true | _ -> false

let trim (s:string) : string =
  let n = String.length s in
  let i = ref 0 in
  while !i < n && is_space s.[!i] do incr i done;
  let j = ref (n - 1) in
  while !j >= !i && is_space s.[!j] do decr j done;
  if !j < !i then "" else String.sub s !i (!j - !i + 1)

let url_decode (s:string) : string =
  let buf = Buffer.create (String.length s) in
  let hex_val c =
    match c with
    | '0'..'9' -> Char.code c - Char.code '0'
    | 'a'..'f' -> 10 + Char.code c - Char.code 'a'
    | 'A'..'F' -> 10 + Char.code c - Char.code 'A'
    | _ -> 0
  in
  let i = ref 0 in
  while !i < String.length s do
    match s.[!i] with
    | '+' -> Buffer.add_char buf ' '; incr i
    | '%' when !i + 2 < String.length s ->
        let a = hex_val s.[!i+1] in
        let b = hex_val s.[!i+2] in
        Buffer.add_char buf (Char.chr (a * 16 + b));
        i := !i + 3
    | c -> Buffer.add_char buf c; incr i
  done;
  Buffer.contents buf

let split_on (ch:char) (s:string) : string list =
  let rec loop acc i j =
    if j = String.length s then
      List.rev ((String.sub s i (j-i)) :: acc)
    else if s.[j] = ch then
      loop ((String.sub s i (j-i)) :: acc) (j+1) (j+1)
    else
      loop acc i (j+1)
  in
  if s = "" then [] else loop [] 0 0

let parse_form_urlencoded (body:string) : (string, string) Hashtbl.t =
  let tbl = Hashtbl.create 16 in
  let pairs = split_on '&' body in
  List.iter
    (fun p ->
      match split_on '=' p with
      | [k; v] -> Hashtbl.replace tbl (url_decode k) (url_decode v)
      | [k] -> Hashtbl.replace tbl (url_decode k) ""
      | _ -> ())
    pairs;
  tbl

let read_line_opt (ic:in_channel) : string option =
  try Some (input_line ic) with End_of_file -> None

let read_headers (ic:in_channel) : (string, string) Hashtbl.t =
  let h = Hashtbl.create 16 in
  let rec loop () =
    match read_line_opt ic with
    | None -> h
    | Some line ->
        let line = trim line in
        if line = "" then h
        else begin
          match split_on ':' line with
          | key :: rest ->
              let v = String.concat ":" rest |> trim in
              Hashtbl.replace h (String.lowercase_ascii (trim key)) v;
              loop ()
          | _ -> loop ()
        end
  in
  loop ()

let read_exactly (ic:in_channel) (n:int) : string =
  really_input_string ic n

let http_response ?(code=200) ?(content_type="text/plain; charset=utf-8") (body:string) : string =
  let reason = match code with
    | 200 -> "OK"
    | 400 -> "Bad Request"
    | 404 -> "Not Found"
    | 500 -> "Internal Server Error"
    | _ -> "OK"
  in
  Printf.sprintf
    "HTTP/1.1 %d %s\r\nContent-Type: %s\r\nContent-Length: %d\r\nConnection: close\r\n\r\n%s"
    code reason content_type (String.length body) body

let json_escape (s:string) : string =
  let b = Buffer.create (String.length s + 16) in
  String.iter
    (fun c ->
      match c with
      | '"' -> Buffer.add_string b "\\\""
      | '\\' -> Buffer.add_string b "\\\\"
      | '\n' -> Buffer.add_string b "\\n"
      | '\r' -> Buffer.add_string b "\\r"
      | '\t' -> Buffer.add_string b "\\t"
      | _ -> Buffer.add_char b c)
    s;
  Buffer.contents b

let read_file (path:string) : string =
  let ic = open_in path in
  let len = in_channel_length ic in
  let s = really_input_string ic len in
  close_in ic;
  s

let html_index () : string =
  "<!doctype html>\n" ^
  "<html>\n" ^
  "<head>\n" ^
  "  <meta charset='utf-8'>\n" ^
  "  <title>AIPL Web Gateway</title>\n" ^
  "</head>\n" ^
  "<body style='font-family:sans-serif'>\n" ^
  "  <h2>AIPL Web Gateway</h2>\n" ^
  "  <p>Send a message to an actor in the running AIPL process.</p>\n" ^
  "\n" ^
  "  <div style='display:flex; gap:24px; align-items:flex-start'>\n" ^
  "    <div>\n" ^
  "      <h3>Direct send (JSON)</h3>\n" ^
  "      <label>to (actor name): <input id='to' value='calc'></label><br>\n" ^
  "      <label>method: <input id='method' value='add'></label><br>\n" ^
  "      <label>args (comma sep): <input id='args' value='1,2'></label><br>\n" ^
  "      <label><input type='checkbox' id='unsafe'> unsafe (skip typecheck)</label><br>\n" ^
  "      <button onclick='send()'>Send</button>\n" ^
  "\n" ^ "      <pre id='out' style='background:#f4f4f4; padding:8px; min-height:2em'></pre>\n" ^
  "\n" ^
  "      <h4>Actor log</h4>\n" ^
  "      <pre id='log' style='background:#111; color:#0f0; padding:8px; min-height:8em; max-height:20em; overflow:auto'></pre>\n" ^
  "\n" ^
  "      <h4>Events</h4>\n" ^
  "      <div id='events' style='background:#222; color:#ff0; padding:8px; min-height:6em; max-height:14em; overflow:auto; font-family:monospace'></div>\n" ^
  "\n" ^
  "      <h4>Replies</h4>\n" ^
  "      <pre id='replies' style='background:#eef; padding:8px; min-height:4em; max-height:10em; overflow:auto'></pre>\n" ^
  "\n" ^
  "      <h4>Message Tree</h4>\n" ^
  "      <div id='tree' style='background:#111; color:#ddd; padding:8px; min-height:8em; max-height:24em; overflow:auto; font-family:monospace'></div>\n" ^
  "    </div>\n" ^
  "  </div>\n" ^
  "\n" ^
  "  <script src='/app.js'></script>\n" ^
  "</body>\n" ^
  "</html>\n"

(*
let html_index () : string =
  "<!doctype html>\n" ^
  "<html><head><meta charset='utf-8'><title>AIPL Web Gateway</title></head>\n" ^
  "<body style='font-family: sans-serif'>\n" ^
  "<h2>AIPL Web Gateway</h2>\n" ^
  "<p>Send a message to an actor in the running AIPL process.</p>\n" ^
  "<div style='display:flex; gap:24px; align-items:flex-start'>\n" ^
  "<div>\n" ^
  "<h3>Direct send (JSON)</h3>\n" ^
  "<label>to (actor name): <input id='to' value='calc'></label><br>\n" ^
  "<label>method: <input id='method' value='add'></label><br>\n" ^
  "<label>args (comma sep): <input id='args' value='1,2'></label><br>\n" ^
  "<label><input type='checkbox' id='unsafe'> unsafe (skip typecheck)</label><br>\n" ^
  "<button onclick='send()'>Send</button>\n" ^
  "<pre id='out' style='background:#f4f4f4; padding:8px; min-height:2em'></pre>\n" ^
  "<h4>Actor log</h4>\n" ^
  "<pre id='log' style='background:#111; color:#0f0; padding:8px; min-height:8em; max-height:20em; overflow:auto'></pre>\n" ^
  "<h4>Events</h4>\n" ^
   "<div id='events' style='background:#222; color:#ff0; padding:8px; min-height:6em; max-height:14em; overflow:auto; font-family: monospace'></div>\n" ^
  "<h4>Replies</h4>\n" ^
  "<pre id='replies' style='background:#eef; padding:8px; min-height:4em; max-height:10em; overflow:auto'></pre>\n" ^
  "<h4>Message Tree</h4>\n" ^
  "<div id='tree' style='background:#111; color:#ddd; padding:8px; min-height:8em; max-height:24em; overflow:auto; font-family: monospace'></div>\n" ^
  "</div>\n" ^
  "</div>\n" ^
  "<script src='/app.js'></script>\n" ^
  "</body></html>\n"
*)
  
(* ---------- Minimal JSON (only what we need) ---------- *)

type jv =
  | JObject of (string * jv) list
  | JArray of jv list
  | JString of string
  | JNumber of float
  | JBool of bool
  | JNull

exception Json_error of string

let json_error msg = raise (Json_error msg)

let parse_json (s:string) : jv =
  let n = String.length s in
  let i = ref 0 in
  let peek () = if !i < n then Some s.[!i] else None in
  let next () = let c = peek () in (match c with Some _ -> incr i | None -> ()); c in
  let rec skip_ws () =
    while !i < n && is_space s.[!i] do incr i done
  in
  let expect ch =
    skip_ws (); match next () with
    | Some c when c = ch -> ()
    | Some c -> json_error (Printf.sprintf "expected '%c' but got '%c'" ch c)
    | None -> json_error (Printf.sprintf "expected '%c' but got EOF" ch)
  in
  let rec parse_string () : string =
    expect '"';
    let buf = Buffer.create 32 in
    let rec loop () =
      match next () with
      | None -> json_error "unterminated string"
      | Some '"' -> Buffer.contents buf
      | Some '\\' ->
          (match next () with
           | Some '"' -> Buffer.add_char buf '"'
           | Some '\\' -> Buffer.add_char buf '\\'
           | Some 'n' -> Buffer.add_char buf '\n'
           | Some 'r' -> Buffer.add_char buf '\r'
           | Some 't' -> Buffer.add_char buf '\t'
           | Some c -> Buffer.add_char buf c
           | None -> json_error "bad escape") ;
          loop ()
      | Some c -> Buffer.add_char buf c; loop ()
    in
    loop ()
  in
  let rec parse_number () : float =
    skip_ws ();
    let start = !i in
    let is_num_char = function
      | '0'..'9' | '-' | '+' | '.' | 'e' | 'E' -> true
      | _ -> false
    in
    while !i < n && is_num_char s.[!i] do incr i done;
    if !i = start then json_error "expected number";
    let sub = String.sub s start (!i - start) in
    match float_of_string_opt sub with
    | Some f -> f
    | None -> json_error ("bad number: " ^ sub)
  in
  let rec parse_value () : jv =
    skip_ws ();
    match peek () with
    | None -> json_error "unexpected EOF"
    | Some '"' -> JString (parse_string ())
    | Some '{' -> parse_object ()
    | Some '[' -> parse_array ()
    | Some 't' ->
        if !i + 3 < n && String.sub s !i 4 = "true" then (i := !i + 4; JBool true)
        else json_error "bad token"
    | Some 'f' ->
        if !i + 4 < n && String.sub s !i 5 = "false" then (i := !i + 5; JBool false)
        else json_error "bad token"
    | Some 'n' ->
        if !i + 3 < n && String.sub s !i 4 = "null" then (i := !i + 4; JNull)
        else json_error "bad token"
    | Some ('0'..'9' | '-') -> JNumber (parse_number ())
    | Some c -> json_error (Printf.sprintf "unexpected char: %c" c)
  and parse_array () : jv =
    expect '[';
    skip_ws ();
    let rec loop acc =
      skip_ws ();
      match peek () with
      | Some ']' -> ignore (next ()); JArray (List.rev acc)
      | _ ->
          let v = parse_value () in
          skip_ws ();
          (match peek () with
           | Some ',' -> ignore (next ()); loop (v :: acc)
           | Some ']' -> ignore (next ()); JArray (List.rev (v :: acc))
           | _ -> json_error "expected , or ]")
    in
    loop []
  and parse_object () : jv =
    expect '{';
    skip_ws ();
    let rec loop acc =
      skip_ws ();
      match peek () with
      | Some '}' -> ignore (next ()); JObject (List.rev acc)
      | Some '"' ->
          let k = parse_string () in
          skip_ws (); expect ':';
          let v = parse_value () in
          skip_ws ();
          (match peek () with
           | Some ',' -> ignore (next ()); loop ((k, v) :: acc)
           | Some '}' -> ignore (next ()); JObject (List.rev ((k, v) :: acc))
           | _ -> json_error "expected , or }")
      | _ -> json_error "expected object key"
    in
    loop []
  in
  let v = parse_value () in
  skip_ws (); if !i <> n then json_error "trailing characters";
  v

let json_get (k:string) (o:(string * jv) list) : jv option = List.assoc_opt k o

let json_get_string (k:string) (o:(string * jv) list) : string option =
  match json_get k o with Some (JString s) -> Some s | _ -> None

let json_get_array (k:string) (o:(string * jv) list) : jv list option =
  match json_get k o with Some (JArray xs) -> Some xs | _ -> None

let json_get_bool (k:string) (o:(string * jv) list) : bool option =
  match List.assoc_opt k o with
  | Some (JBool b) -> Some b
  | _ -> None

let rec jv_to_json (v:jv) : string =
  match v with
  | JNull -> "null"
  | JBool true -> "true"
  | JBool false -> "false"
  | JNumber n ->
      if Float.is_finite n && abs_float (n -. Float.floor n) < 1e-9
      then string_of_int (int_of_float (Float.round n))
      else Printf.sprintf "%g" n
  | JString s -> "\"" ^ json_escape s ^ "\""
  | JArray xs -> "[" ^ String.concat "," (List.map jv_to_json xs) ^ "]"
  | JObject kvs ->
      "{" ^
      String.concat ","
        (List.map
           (fun (k,v) -> "\"" ^ json_escape k ^ "\":" ^ jv_to_json v)
           kvs)
      ^ "}"

(* Push a bridge frame to all WS clients subscribed to sid="bridge". Used when
   an incoming /api/json/send targets an actor that doesn't exist locally: the
   frame lets a browser-hosted actor runtime pick up the message and deliver
   it to its in-browser mailbox. *)
let push_bridge ~(to_:string) ~(meth:string) ~(args_json:jv list) ~(from:string) : unit =
  let args_s = String.concat "," (List.map jv_to_json args_json) in
  let frame =
    Printf.sprintf
      {|{"type":"bridge","to":"%s","method":"%s","args":[%s],"from":"%s"}|}
      (json_escape to_) (json_escape meth) args_s (json_escape from)
  in
  ws_send_to_sid "bridge" (fun oc -> ws_send_text oc frame)

let ast_of_json_value (v:jv) : Ast.expr =
  match v with
  | JString s -> Ast.mk_expr (Ast.String s)
  | JBool b -> Ast.mk_expr (Ast.String (if b then "true" else "false"))
  | JNumber f ->
      (* If it's integral, prefer Int. *)
      if Float.is_finite f && abs_float (f -. Float.floor f) < 1e-9
      then Ast.mk_int (int_of_float (Float.round f))
      else Ast.mk_float f
  | JNull -> Ast.mk_expr (Ast.String "")
  | JObject _ | JArray _ -> Ast.mk_expr (Ast.String "")

(* ---------- Type checking for web calls (best-effort) ---------- *)

let type_matches (param:Types.ty) (arg:Ast.expr) : bool * Ast.expr =
  (* return (ok, maybe-coerced-arg) *)
  let param = Types.repr param in
  match param, arg.desc with
  | TInt, Int _ -> (true, arg)
  | TFloat, Float _ -> (true, arg)
  | TFloat, Int i -> (true, Ast.mk_float (float_of_int i)) (* allow int->float *)
  | TString, String _ -> (true, arg)
  | TBool, String "true"  -> (true, arg)
  | TBool, String "false" -> (true, arg)
  | TBool, Int 0 -> (true, arg)
  | TBool, Int 1 -> (true, arg)
(*  | TBool, Bool _ -> (true, arg) *)
  | TVar _, _ -> (true, arg) (* polymorphic: accept *)
  | _, _ -> (false, arg)

let check_web_call ~(actor_name:string) ~(method_name:string) (args:Ast.expr list) : (bool * string * Ast.expr list) =
  match Eval_thread.lookup_actor_class actor_name with
  | None -> (false, "unknown actor: " ^ actor_name, args)
  | Some cls ->
      (match Types.lookup_class_method_scheme cls method_name with
       | None -> (false, Printf.sprintf "unknown method: %s.%s" cls method_name, args)
       | Some (Forall (_, ty)) ->
           (match Types.repr ty with
            | TFun (params, _ret) ->
                if List.length params <> List.length args then
                  (false, Printf.sprintf "arity mismatch: expected %d args" (List.length params), args)
                else
                  let ok = ref true in
                  let coerced =
                    List.map2
                      (fun p a ->
                        let (b, a2) = type_matches p a in
                        if not b then ok := false;
                        a2)
                      params args
                  in
                  if !ok then (true, "", coerced)
                  else (false, "type mismatch", args)
            | _ -> (true, "", args)))

let parse_args_to_exprs (args_s:string) : Ast.expr list =
  let items =
    args_s
    |> split_on ','
    |> List.map trim
    |> List.filter (fun s -> s <> "")
  in
  let parse_one (s:string) : Ast.expr =
    (* try int, then float, else string *)
    let s0 = trim s in
    let unquoted =
      let n = String.length s0 in
      if n >= 2 && ((s0.[0] = '"' && s0.[n-1] = '"') || (s0.[0] = '\'' && s0.[n-1] = '\''))
      then String.sub s0 1 (n-2)
      else s0
    in
    match int_of_string_opt unquoted with
    | Some i -> Ast.mk_int i
    | None ->
        (match float_of_string_opt unquoted with
         | Some f -> Ast.mk_float f
         | None -> Ast.mk_expr (Ast.String unquoted))
  in
  List.map parse_one items

let handle_send_direct (params:(string, string) Hashtbl.t) : (int * string * string) =
  let get k = match Hashtbl.find_opt params k with Some v -> v | None -> "" in
  let to_ = get "to" in
  let meth = get "method" in
  let args = get "args" in
  let from_ = let f = get "from" in if f = "" then "<web>" else f in
  if to_ = "" || meth = "" then
    (400, "text/plain; charset=utf-8", "missing to/method")
  else
    let exprs = parse_args_to_exprs args in
    (try
       Eval_thread.send_message ~from:from_ to_ (mk_stmt (CallStmt (meth, exprs)));
       (200, "text/plain; charset=utf-8", "OK")
     with exn ->
       (500, "text/plain; charset=utf-8", "error: " ^ Printexc.to_string exn))

let handle_send_exposed ~(key:string) (params:(string, string) Hashtbl.t) : (int * string * string) =
  match Hashtbl.find_opt exposed key with
  | None -> (404, "text/plain; charset=utf-8", "unknown endpoint: " ^ key)
  | Some actor_name ->
      let get k = match Hashtbl.find_opt params k with Some v -> v | None -> "" in
      let meth = get "method" in
      let args = get "args" in
      let from_ = let f = get "from" in if f = "" then "<web>" else f in
      if meth = "" then
        (400, "text/plain; charset=utf-8", "missing method")
      else
        let exprs = parse_args_to_exprs args in
        (try
           Eval_thread.send_message ~from:from_ actor_name (mk_stmt (CallStmt (meth, exprs)));
           (200, "text/plain; charset=utf-8", "OK")
         with exn ->
           (500, "text/plain; charset=utf-8", "error: " ^ Printexc.to_string exn))

let sid_to_actor : (string, string) Hashtbl.t = Hashtbl.create 256
let sid_actor_mu = Mutex.create ()

let actor_for_sid ~(sid:string) ~(base:string) : string =
  Mutex.lock sid_actor_mu;
  let name =
    match Hashtbl.find_opt sid_to_actor (sid ^ "|" ^ base) with
    | Some a -> a
    | None ->
        let a = base ^ "_" ^ sid in
        Hashtbl.add sid_to_actor (sid ^ "|" ^ base) a;
        a
  in
  Mutex.unlock sid_actor_mu;
  name

let handle_api_repl (body:string) : (int * string * string) =
  try
    match parse_json body with
    | JObject o ->
        let cmd =
          match json_get_string "command" o with
          | Some s -> s
          | None -> ""
        in
        if cmd = "" then
          (400, "text/plain; charset=utf-8", "missing command")
        else
          (match !repl_command_handler with
           | None ->
               (500, "text/plain; charset=utf-8",
                "repl handler is not registered")
           | Some f ->
               let result =
                 try f cmd
                 with exn -> "[ERROR] " ^ Printexc.to_string exn
               in
               (200, "text/plain; charset=utf-8", result))
    | _ ->
        (400, "text/plain; charset=utf-8", "JSON must be an object")
  with
  | Json_error m ->
      (400, "text/plain; charset=utf-8", "bad JSON: " ^ m)
  | exn ->
      (500, "text/plain; charset=utf-8", "error: " ^ Printexc.to_string exn)
  
let handle_send_direct_json (body:string) : (int * string * string) =
  try
    match parse_json body with
    | JObject o ->
        let to_ = match json_get_string "to" o with Some s -> s | None -> "" in
        let meth = match json_get_string "method" o with Some s -> s | None -> "" in
        let from_ = match json_get_string "from" o with Some s -> s | None -> "<web>" in
        let sid = match json_get_string "sid" o with Some s -> s | None -> "" in
        let args_json = match json_get_array "args" o with Some xs -> xs | None -> [] in
	let real_to =
	  if Eval_thread.actor_exists to_ then to_
	  else if sid <> "" then actor_for_sid ~sid ~base:to_
	  else to_
	in
	let unsafe = match json_get_bool "unsafe" o with Some b -> b | None -> false in
        if to_ = "" || meth = "" then
          (400, "text/plain; charset=utf-8", "missing to/method")
        else if sid = ""
             && not (Eval_thread.actor_exists real_to)
             && ws_sid_has_clients "bridge" then (
          (* Local actor doesn't exist, but a browser is subscribed to the
             bridge — forward this as a remote send so the browser-side
             runtime delivers it to its in-browser actor. *)
          push_bridge ~to_:real_to ~meth ~args_json ~from:from_;
          Eval_thread.push_web_evt
            (Printf.sprintf "[BRIDGE->web] to=%s.%s from=%s" real_to meth from_);
          (200, "text/plain; charset=utf-8", "bridged")
        ) else
          let exprs = List.map ast_of_json_value args_json in
          if sid <> "" && real_to <> to_ then (
            if not (Eval_thread.actor_exists real_to) then
            Eval_thread.spawn_actor ~class_name:"Calc" ~actor_name:real_to
          );
          let (ok, msg, exprs2) =
            if unsafe then (true, "", exprs)
            else check_web_call ~actor_name:real_to ~method_name:meth exprs in
            if not ok then (
              Eval_thread.push_web_evt
                (Printf.sprintf "[FAILED] to=%s.%s reason=typecheck:%s" real_to meth msg);
              (400, "text/plain; charset=utf-8", "typecheck failed: " ^ msg)
          ) else (
           let msg_id = Printf.sprintf "m-%d" (int_of_float (Unix.time () *. 1000.0)) in
             if sid <> "" then bind_msgid_sid msg_id sid;
             Eval_thread.push_web_evt
               (Printf.sprintf "[ACCEPTED] id=%s to=%s.%s" msg_id real_to meth);
           try
             Eval_thread.send_message ~msg_id ~from:from_ real_to (mk_stmt (CallStmt (meth, exprs2)));
             (200, "text/plain; charset=utf-8", "OK")
           with exn ->
             Eval_thread.push_web_evt
               (Printf.sprintf "[FAILED] id=%s to=%s.%s reason=%s"
               msg_id real_to meth (Printexc.to_string exn));
             (500, "text/plain; charset=utf-8", "error: " ^ Printexc.to_string exn)
         )
    | _ ->
        (400, "text/plain; charset=utf-8", "JSON must be an object")
 with
  | Json_error m ->
      (400, "text/plain; charset=utf-8", "bad JSON: " ^ m)
  | exn ->
      (* ★ これが無いと ERR_EMPTY_RESPONSE になる *)
      (500, "text/plain; charset=utf-8", "error: " ^ Printexc.to_string exn)

(* Synchronous remote call.  Dispatches the message with a unique
   msg_id, then blocks the HTTP response until the actor's reply()
   resolves the matching slot (or the timeout expires — then null).
   Wire-compatible with the Python runtime's /api/json/call. *)

let next_call_msg_id =
  let counter = ref 0 in
  fun () ->
    let n = !counter in
    counter := n + 1;
    Printf.sprintf "call-%d-%d"
      (int_of_float (Unix.gettimeofday () *. 1000.0)) n

let handle_call_direct_json (body:string) (q:(string,string) Hashtbl.t)
    : (int * string * string) =
  try
    match parse_json body with
    | JObject o ->
        let to_   = match json_get_string "to"     o with Some s -> s | None -> "" in
        let meth  = match json_get_string "method" o with Some s -> s | None -> "" in
        let from_ = match json_get_string "from"   o with Some s -> s | None -> "<web>" in
        let args_json = match json_get_array "args" o with Some xs -> xs | None -> [] in
        let timeout_s =
          match Hashtbl.find_opt q "timeout_ms" with
          | Some s -> (try float_of_string s /. 1000.0 with _ -> 30.0)
          | None -> 30.0
        in
        if to_ = "" || meth = "" then
          (400, "text/plain; charset=utf-8", "missing to/method")
        else if not (Eval_thread.actor_exists to_) then
          (404, "text/plain; charset=utf-8", "no such actor: " ^ to_)
        else
          let exprs = List.map ast_of_json_value args_json in
          let msg_id = next_call_msg_id () in
          let slot = register_reply_slot msg_id in
          Eval_thread.send_message ~msg_id ~from:from_ to_
            (Ast.mk_stmt (Ast.CallStmt (meth, exprs)));
          let v = wait_reply_slot slot ~timeout_s in
          unregister_reply_slot msg_id;
          let reply_json = match v with Some s -> s | None -> "null" in
          let body_resp =
            Printf.sprintf {|{"ok":true,"reply":%s}|} reply_json
          in
          (200, "application/json", body_resp)
    | _ -> (400, "text/plain; charset=utf-8", "expected JSON object")
  with _ -> (400, "text/plain; charset=utf-8", "bad request")

let handle_send_exposed_json ~(key:string) (body:string) : (int * string * string) =
  match Hashtbl.find_opt exposed key with
  | None ->
      (404, "text/plain; charset=utf-8", "unknown endpoint: " ^ key)
  | Some actor_name ->
      try
        match parse_json body with
        | JObject o ->
	    let to_ = match json_get_string "to" o with Some s -> s | None -> "" in
            let meth = match json_get_string "method" o with Some s -> s | None -> "" in
            let from_ = match json_get_string "from" o with Some s -> s | None -> "<web>" in
            let args_json = match json_get_array "args" o with Some xs -> xs | None -> [] in
            let sid = match json_get_string "sid" o with Some s -> s | None -> "" in
	    let real_to =
	      if Eval_thread.actor_exists to_ then to_
	      else if sid <> "" then actor_for_sid ~sid ~base:to_
	      else to_
	    in
	    let unsafe = match json_get_bool "unsafe" o with Some b -> b | None -> false in

            if to_ = "" || meth = "" then
              (400, "text/plain; charset=utf-8", "missing method")
            else
              let exprs = List.map ast_of_json_value args_json in
              if sid <> "" && real_to <> to_ then (
                if not (Eval_thread.actor_exists real_to) then
                  Eval_thread.spawn_actor ~class_name:"Calculator" ~actor_name:real_to
              );
              let (ok, msg, exprs2) =
                if unsafe then (true, "", exprs)
                else check_web_call ~actor_name:real_to ~method_name:meth exprs
              in
              if not ok then (
                Eval_thread.push_web_evt
                  (Printf.sprintf "[FAILED] to=%s.%s reason=typecheck:%s" actor_name meth msg);
                (400, "text/plain; charset=utf-8", "typecheck failed: " ^ msg)
              ) else (
                let msg_id =
                  Printf.sprintf "m-%d" (int_of_float (Unix.time () *. 1000.0))
                in
                if sid <> "" then bind_msgid_sid msg_id sid;
                Eval_thread.push_web_evt
                  (Printf.sprintf "[ACCEPTED] id=%s to=%s.%s" msg_id actor_name meth);
                try
		  Eval_thread.send_message ~msg_id ~from:from_ actor_name (mk_stmt (CallStmt (meth, exprs2)));
                  (200, "text/plain; charset=utf-8", "OK")
                with exn ->
                 Eval_thread.push_web_evt
                    (Printf.sprintf "[FAILED] id=%s to=%s.%s reason=%s"
                       msg_id actor_name meth (Printexc.to_string exn));
                  (500, "text/plain; charset=utf-8", "error: " ^ Printexc.to_string exn)
              )
        | _ ->
            (400, "text/plain; charset=utf-8", "JSON must be an object")
 with
  | Json_error m ->
      (400, "text/plain; charset=utf-8", "bad JSON: " ^ m)
  | exn ->
      (* ★ これが無いと ERR_EMPTY_RESPONSE になる *)
      (500, "text/plain; charset=utf-8", "error: " ^ Printexc.to_string exn)

let handle_api_log (query:(string,string) Hashtbl.t) =
  let sid =
    match Hashtbl.find_opt query "sid" with
    | Some s -> s
    | None -> ""
  in
  let after =
    match Hashtbl.find_opt query "after" with
    | Some s -> (try int_of_string s with _ -> -1)
    | None -> -1
  in

  (* sid が無い場合は global の web_logs を返す（Server Console 用） *)
  let (next_id, lines) =
    if sid = "" then Eval_thread.get_web_logs_since after
    else Eval_thread.get_sid_logs_since sid after
    in
     let esc s =
    let b = Buffer.create (String.length s + 8) in
    String.iter (function
      | '"' -> Buffer.add_string b "\\\""
      | '\\' -> Buffer.add_string b "\\\\"
      | '\n' -> Buffer.add_string b "\\n"
      | '\r' -> Buffer.add_string b "\\r"
      | '\t' -> Buffer.add_string b "\\t"
      | c -> Buffer.add_char b c
    ) s;
    Buffer.contents b
  in
  let body =
    Printf.sprintf {|{"next":%d,"lines":[%s]}|}
      next_id
      (String.concat "," (List.map (fun s -> "\"" ^ esc s ^ "\"") lines))
  in
  (200, "application/json; charset=utf-8", body)
	  
(*
   let handle_api_log query =
  let after =
    match Hashtbl.find_opt query "after" with
    | Some s -> (try int_of_string s with _ -> 0)
    | None -> 0
  in
  let (next_id, lines) = Eval_thread.get_web_logs_since after in
  let esc s =
    let b = Buffer.create (String.length s + 8) in
    String.iter (function
      | '"' -> Buffer.add_string b "\\\""
      | '\\' -> Buffer.add_string b "\\\\"
      | '\n' -> Buffer.add_string b "\\n"
      | '\r' -> Buffer.add_string b "\\r"
      | c -> Buffer.add_char b c
    ) s;
    Buffer.contents b
  in
  let body =
    Printf.sprintf
      {|{"next":%d,"lines":[%s]}|}
      next_id
      (String.concat "," (List.map (fun s -> "\"" ^ esc s ^ "\"") lines))
  in
  (200, "application/json; charset=utf-8", body)
*)

let handle_api_events (query:(string,string) Hashtbl.t) =
  let after =
    match Hashtbl.find_opt query "after" with
    | Some s -> (try int_of_string s with _ -> 0)
    | None -> 0
  in
  let (next_id, lines) = Eval_thread.get_web_evts_since after in
  let esc s =
    let b = Buffer.create (String.length s + 8) in
    String.iter (function
      | '"' -> Buffer.add_string b "\\\""
      | '\\' -> Buffer.add_string b "\\\\"
      | '\n' -> Buffer.add_string b "\\n"
      | '\r' -> Buffer.add_string b "\\r"
      | '\t' -> Buffer.add_string b "\\t"
      | c -> Buffer.add_char b c
    ) s;
    Buffer.contents b
  in
  let body =
    Printf.sprintf {|{"next":%d,"lines":[%s]}|}
      next_id
      (String.concat "," (List.map (fun s -> "\"" ^ esc s ^ "\"") lines))
  in
  (200, "application/json; charset=utf-8", body)

(* ---- IDE helper endpoints ---- *)

(* Small JSON-string escaper reused by /api/actors and /api/browse. *)
let json_str_esc (s:string) : string =
  let b = Buffer.create (String.length s + 8) in
  String.iter (function
    | '"' -> Buffer.add_string b "\\\""
    | '\\' -> Buffer.add_string b "\\\\"
    | '\n' -> Buffer.add_string b "\\n"
    | '\r' -> Buffer.add_string b "\\r"
    | '\t' -> Buffer.add_string b "\\t"
    | c -> Buffer.add_char b c
  ) s;
  Buffer.contents b

(* Return the current actor table as structured JSON. This is the
   counterpart of the REPL `actors` command, but designed for the IDE:
   it does not write anything to stdout and does not go through the
   REPL buffer, so polling it does not flood the server terminal. *)
let handle_api_actors () : int * string * string =
  let buf = Buffer.create 256 in
  Buffer.add_char buf '[';
  let first = ref true in
  Eval_thread.iter_actor_table (fun aname a ->
    let cls = Eval_thread.actor_class_name aname a in
    let mbox_n = Eval_thread.mailbox_len a in
    let mnames = Eval_thread.method_names a in
    let ty_str =
      let ms = Types.lookup_class_methods_inst cls in
      if ms = [] then "actor(" ^ cls ^ ")"
      else Types.string_of_ty_pretty (Types.TActor (cls, ms))
    in
    if not !first then Buffer.add_char buf ',';
    first := false;
    let methods_json =
      String.concat ","
        (List.map (fun m -> "\"" ^ json_str_esc m ^ "\"") mnames)
    in
    Buffer.add_string buf
      (Printf.sprintf
         {|{"name":"%s","class":"%s","type":"%s","mbox":%d,"methods":[%s]}|}
         (json_str_esc aname) (json_str_esc cls) (json_str_esc ty_str)
         mbox_n methods_json)
  );
  Buffer.add_char buf ']';
  (200, "application/json; charset=utf-8", Buffer.contents buf)

(* Browse a directory. Returns subdirs and files in the requested dir,
   with an optional extension filter. Used by the IDE's File menu to let
   users pick their own .bat / .abcl files from anywhere on disk. *)
let handle_api_browse (query:(string,string) Hashtbl.t) : int * string * string =
  let dir_raw =
    match Hashtbl.find_opt query "dir" with
    | Some s -> s
    | None -> "."
  in
  let ext_filter =
    match Hashtbl.find_opt query "ext" with
    | Some s -> String.lowercase_ascii (trim s)
    | None -> ""
  in
  let dir =
    let d = trim dir_raw in
    if d = "" then "." else d
  in
  (* Expand a leading "~/" to the user's home. *)
  let dir =
    if String.length dir >= 2 && dir.[0] = '~' && dir.[1] = '/' then
      try
        let home = Sys.getenv "HOME" in
        home ^ String.sub dir 1 (String.length dir - 1)
      with Not_found -> dir
    else dir
  in
  let has_ext name =
    if ext_filter = "" then true
    else
      let nlen = String.length name in
      let elen = String.length ext_filter + 1 in
      nlen > elen
      && String.lowercase_ascii (String.sub name (nlen - elen) elen)
         = ("." ^ ext_filter)
  in
  try
    let entries = Sys.readdir dir in
    Array.sort compare entries;
    let dirs  = ref [] in
    let files = ref [] in
    Array.iter (fun name ->
      if name = "" || name.[0] = '.' then ()  (* hide dotfiles by default *)
      else begin
        let path =
          if dir = "." then name
          else if dir = "/" then "/" ^ name
          else dir ^ "/" ^ name
        in
        try
          if Sys.is_directory path then dirs := name :: !dirs
          else if has_ext name then files := name :: !files
        with _ -> ()
      end
    ) entries;
    let dirs  = List.rev !dirs in
    let files = List.rev !files in
    (* Compute absolute path for display and a reasonable parent. *)
    let abs_dir =
      try
        if Filename.is_relative dir then
          Filename.concat (Sys.getcwd ()) dir
        else dir
      with _ -> dir
    in
    (* Normalize trailing "/." (arises from Filename.concat cwd ".") so the
       path joins cleanly on the client side. *)
    let abs_dir =
      let n = String.length abs_dir in
      if n >= 2 && abs_dir.[n-1] = '.' && abs_dir.[n-2] = '/'
      then (if n = 2 then "/" else String.sub abs_dir 0 (n-2))
      else abs_dir
    in
    let abs_dir =
      let n = String.length abs_dir in
      if n > 1 && abs_dir.[n-1] = '/' then String.sub abs_dir 0 (n-1)
      else abs_dir
    in
    let parent =
      let strip_trailing_slash s =
        let n = String.length s in
        if n > 1 && s.[n-1] = '/' then String.sub s 0 (n-1) else s
      in
      let d = strip_trailing_slash abs_dir in
      if d = "/" then "" else Filename.dirname d
    in
    let json_list xs =
      "[" ^
      String.concat ","
        (List.map (fun s -> "\"" ^ json_str_esc s ^ "\"") xs)
      ^ "]"
    in
    let body =
      Printf.sprintf
        {|{"dir":"%s","abs":"%s","parent":"%s","ext":"%s","dirs":%s,"files":%s}|}
        (json_str_esc dir) (json_str_esc abs_dir) (json_str_esc parent)
        (json_str_esc ext_filter) (json_list dirs) (json_list files)
    in
    (200, "application/json; charset=utf-8", body)
  with
  | Sys_error msg ->
      let body =
        Printf.sprintf {|{"error":"%s","dir":"%s"}|}
          (json_str_esc msg) (json_str_esc dir)
      in
      (400, "application/json; charset=utf-8", body)
  | exn ->
      let body =
        Printf.sprintf {|{"error":"%s"}|}
          (json_str_esc (Printexc.to_string exn))
      in
      (500, "application/json; charset=utf-8", body)

(* List project files matching an extension. Used by the IDE's File menu to
   populate the list of available .bat / .abcl scripts. We only look at a
   small fixed set of project-relative directories so that this cannot be
   turned into an arbitrary directory browser. *)
let handle_api_files (query:(string,string) Hashtbl.t) : int * string * string =
  let ext =
    match Hashtbl.find_opt query "ext" with
    | Some s -> String.lowercase_ascii (trim s)
    | None -> "bat"
  in
  let ext = if ext = "" then "bat" else ext in
  let has_ext name =
    let elen = String.length ext + 1 in
    let nlen = String.length name in
    nlen > elen
    && String.lowercase_ascii (String.sub name (nlen - elen) elen) = ("." ^ ext)
  in
  let search_dirs = [ "abclc"; "src"; "." ] in
  let collected = ref [] in
  List.iter (fun dir ->
    let dir_candidates = [ dir; "../" ^ dir ] in
    let rec first_readable = function
      | [] -> None
      | d :: rest ->
          (try Some (d, Sys.readdir d) with _ -> first_readable rest)
    in
    match first_readable dir_candidates with
    | None -> ()
    | Some (d, arr) ->
        Array.sort compare arr;
        Array.iter (fun name ->
          if has_ext name then begin
            let path =
              if d = "." then name else d ^ "/" ^ name
            in
            collected := path :: !collected
          end
        ) arr
  ) search_dirs;
  let files = List.rev !collected in
  let esc s =
    let b = Buffer.create (String.length s + 8) in
    String.iter (function
      | '"' -> Buffer.add_string b "\\\""
      | '\\' -> Buffer.add_string b "\\\\"
      | '\n' -> Buffer.add_string b "\\n"
      | c -> Buffer.add_char b c
    ) s;
    Buffer.contents b
  in
  let body =
    Printf.sprintf {|{"ext":"%s","files":[%s]}|}
      (esc ext)
      (String.concat "," (List.map (fun s -> "\"" ^ esc s ^ "\"") files))
  in
  (200, "application/json; charset=utf-8", body)

let handle_ws (client:file_descr) (headers:(string,string) Hashtbl.t) (q:(string,string) Hashtbl.t) : unit =
  let ic = in_channel_of_descr client in
  let oc = out_channel_of_descr client in

  let close_all () =
    (try flush oc with _ -> ());
    (try close_in_noerr ic with _ -> ());
    (try close_out_noerr oc with _ -> ());
    (try Unix.close client with _ -> ())
  in

  (* --- Handshake --- *)
  match Hashtbl.find_opt headers "sec-websocket-key" with
  | None ->
      output_string oc "HTTP/1.1 400 Bad Request\r\nContent-Length:0\r\n\r\n";
      flush oc;
      close_all ()
  | Some key ->
      let accept = ws_accept (trim key) in
      output_string oc "HTTP/1.1 101 Switching Protocols\r\n";
      output_string oc "Upgrade: websocket\r\n";
      output_string oc "Connection: Upgrade\r\n";
      output_string oc ("Sec-WebSocket-Accept: " ^ accept ^ "\r\n");
      output_string oc "\r\n";
      flush oc;

      (* ---- sid from /ws?sid=... ---- *)
      let sid = match Hashtbl.find_opt q "sid" with Some s -> s | None -> "" in
      if sid <> "" then ws_add sid oc;

      (* IMPORTANT: start from -1 so we never miss id=0 items *)
      let log_after = ref (-1) in
      let evt_after = ref (-1) in

      (* We do not parse client->server frames in this minimal version.
         We only detect disconnect by trying to write periodically and by
         reading a byte in a background thread. *)
      let running = ref true in

      let _reader =
        Thread.create
          (fun () ->
             try
               while !running do
                 (* If client closes, input_char will raise. *)
                 ignore (input_char ic)
               done
             with _ ->
               running := false)
          ()
      in

      let send_log_line (line:string) =
        (* send as type=log *)
        ws_send_text oc (Printf.sprintf {|{"type":"log","line":%S}|} line)
      in
(*      let send_event_line (line:string) =
        (* classify reply vs normal event *)
        if String.length line >= 7 && String.sub line 0 7 = "[REPLY]" then
          ws_send_text oc (Printf.sprintf {|{"type":"reply","line":%S}|} line)
        else
          ws_send_text oc (Printf.sprintf {|{"type":"event","line":%S}|} line)
      in    *)
      let extract_id (line:string) : string option =
        let key = "id=" in
        let rec find_from i =
          if i + String.length key > String.length line then None
          else if String.sub line i (String.length key) = key then Some (i + String.length key)
          else find_from (i+1)
        in
        match find_from 0 with
        | None -> None
        | Some j ->
            let k =
              match String.index_from_opt line j ' ' with
              | Some sp -> sp
              | None -> String.length line
            in
            Some (String.sub line j (k - j))
      in

      (try
         while !running do
           (* push logs *)
           let (nlog, logs) = Eval_thread.get_web_logs_since !log_after in
           if logs <> [] then begin
             log_after := nlog;
             List.iter send_log_line logs
         end;

         (* push events (sid-filtered) *)
           let (nevt, evts) = Eval_thread.get_web_evts_since !evt_after in
           if evts <> [] then begin
             evt_after := nevt;

             List.iter (fun line ->
               match extract_id line with
               | None ->
                   ()  (* idが無いイベントは送らない（安全） *)
               | Some mid ->
                   match lookup_sid mid with
                   | None -> ()
                   | Some sid_dst ->
                       ws_send_to_sid sid_dst (fun oc2 ->
                         if String.length line >= 7 && String.sub line 0 7 = "[REPLY]" then
                           ws_send_text oc2 (Printf.sprintf {|{"type":"reply","line":%S}|} line)
                         else
                           ws_send_text oc2 (Printf.sprintf {|{"type":"event","line":%S}|} line)
                       )
             ) evts
           end;

           Thread.delay 0.2
         done
       with _ ->
         running := false);

      (* ---- remove from sid table ---- *)
      if sid <> "" then ws_remove sid oc;

      close_all ()

let read_file (path:string) : string =
  let ic = open_in path in
  let len = in_channel_length ic in
  let s = really_input_string ic len in
  close_in ic;
  s

(* Look for a static asset (app.js etc.) in a few likely locations so the REPL
   serves the web console whether it's launched from the project root or from
   src/. Returns None if no candidate is found. *)
let read_asset (name:string) : string option =
  let candidates = [ name; "src/" ^ name; "../src/" ^ name ] in
  let rec loop = function
    | []      -> None
    | p :: ps -> (try Some (read_file p) with _ -> loop ps)
  in
  loop candidates

let serve_asset (name:string) (ctype:string) : int * string * string =
  match read_asset name with
  | Some body -> (200, ctype, body)
  | None ->
      (404, "text/plain; charset=utf-8",
       "asset not found: " ^ name ^
       " (looked in ., src/, ../src/)")

(* Assets that live under src/browser-abcl/src/ (runtime, interpreter, parser,
   ast) need their own lookup path. *)
let read_browser_asset (rel:string) : string option =
  let candidates = [
    "src/browser-abcl/src/" ^ rel;
    "browser-abcl/src/" ^ rel;
    "../src/browser-abcl/src/" ^ rel;
    "../browser-abcl/src/" ^ rel;
  ] in
  let rec loop = function
    | []      -> None
    | p :: ps -> (try Some (read_file p) with _ -> loop ps)
  in
  loop candidates

let serve_browser_asset (rel:string) (ctype:string) : int * string * string =
  match read_browser_asset rel with
  | Some body -> (200, ctype, body)
  | None ->
      (404, "text/plain; charset=utf-8",
       "browser asset not found: " ^ rel)

let handle_client (client: file_descr) : unit =
  let ic = in_channel_of_descr client in
  let oc = out_channel_of_descr client in
  let safe_write s =
    output_string oc s;
    flush oc
  in
  (try
     match read_line_opt ic with
     | None -> ()
     | Some req_line ->
         let parts = split_on ' ' (trim req_line) in
         let meth, raw_path =
           match parts with
           | m :: p :: _ -> (String.uppercase_ascii m, p)
           | _ -> ("", "/")
         in
         let path, query =
           match split_on '?' raw_path with
           | p :: q :: _ -> (p, q)
           | p :: [] -> (p, "")
           | _ -> (raw_path, "")
         in
         let headers = read_headers ic in
         let content_len =
           match Hashtbl.find_opt headers "content-length" with
           | None -> 0
           | Some v -> (try int_of_string (trim v) with _ -> 0)
         in
         let body = if content_len > 0 then read_exactly ic content_len else "" in
         let parse_query_to_tbl (qs:string) : (string,string) Hashtbl.t =
           let tbl = Hashtbl.create 16 in
           let qs = if qs <> "" && qs.[0] = '?' then String.sub qs 1 (String.length qs - 1)
           else qs
           in
             let pairs = if qs = "" then [] else String.split_on_char '&' qs in
               List.iter (fun kv ->
                 match String.split_on_char '=' kv with
                 | [k; v] -> Hashtbl.replace tbl (url_decode k) (url_decode v)
                 | [k] -> Hashtbl.replace tbl (url_decode k) ""
                 | _ -> ()
               ) pairs;
            tbl in
	 let q : (string,string) Hashtbl.t = parse_query_to_tbl query in
         (* --- WebSocket endpoint: DO NOT write normal HTTP response --- *)
         if meth = "GET" && path = "/ws" then (
           handle_ws client headers q;
           raise Exit
         );
	 let code, ctype, resp_body =
           match meth, path with
	   | "GET", "/" -> (200, "text/html; charset=utf-8", html_index ())
	   | "GET", "/ide" -> serve_asset "ide.html" "text/html; charset=utf-8"
	   | "GET", "/ide.html" -> serve_asset "ide.html" "text/html; charset=utf-8"
	   | "GET", "/ide.js" -> serve_asset "ide.js" "application/javascript; charset=utf-8"
	   | "GET", "/app.js" -> serve_asset "app.js" "application/javascript; charset=utf-8"
           | "GET", "/console_server.js" -> serve_asset "console_server.js" "application/javascript; charset=utf-8"
	   | "GET", "/console_browser.js" -> serve_asset "console_browser.js" "application/javascript; charset=utf-8"
	   | "GET", "/viz_philosophers.html" -> serve_asset "viz_philosophers.html" "text/html; charset=utf-8"
	   | "GET", "/viz_philosophers.js" -> serve_asset "viz_philosophers.js" "application/javascript; charset=utf-8"
	   | "GET", "/viz_philosophers.abcl" -> serve_asset "viz_philosophers.abcl" "text/plain; charset=utf-8"
	   | "GET", "/distributed_philosophers.html" -> serve_asset "distributed_philosophers.html" "text/html; charset=utf-8"
	   | "GET", "/distributed_philosophers.js" -> serve_asset "distributed_philosophers.js" "application/javascript; charset=utf-8"
	   | "GET", "/distributed_philosophers_browser.abcl" -> serve_asset "distributed_philosophers_browser.abcl" "text/plain; charset=utf-8"
	   | "GET", "/distributed_philosophers_ocaml.abcl" -> serve_asset "distributed_philosophers_ocaml.abcl" "text/plain; charset=utf-8"
	   | "GET", "/src/ast.js" -> serve_browser_asset "ast.js" "application/javascript; charset=utf-8"
	   | "GET", "/src/runtime.js" -> serve_browser_asset "runtime.js" "application/javascript; charset=utf-8"
	   | "GET", "/src/interpreter.js" -> serve_browser_asset "interpreter.js" "application/javascript; charset=utf-8"
	   | "GET", "/src/parser/parser.js" -> serve_browser_asset "parser/parser.js" "application/javascript; charset=utf-8"
           | "GET", "/api/log" -> handle_api_log q
	   | "GET", "/api/events" -> handle_api_events q
	   | "GET", "/api/files" -> handle_api_files q
	   | "GET", "/api/actors" -> handle_api_actors ()
	   | "GET", "/api/browse" -> handle_api_browse q
	   | "POST", "/api/send" -> let params = parse_form_urlencoded body in handle_send_direct params
           | "POST", "/api/json/send" ->
               (match verify_hmac_or_reject ~headers ~body with
                | Some err -> err
                | None -> handle_send_direct_json body)
           | "POST", "/api/json/call" ->
               (match verify_hmac_or_reject ~headers ~body with
                | Some err -> err
                | None -> handle_call_direct_json body q)
           | "POST", "/api/repl" -> handle_api_repl body
           | "POST", _ when String.length path >= String.length "/api/x/" &&
                            String.sub path 0 (String.length "/api/x/") = "/api/x/" ->
               let key = String.sub path (String.length "/api/x/") (String.length path - String.length "/api/x/") in
               let params = parse_form_urlencoded body in
               handle_send_exposed ~key params
           | "POST", _ when String.length path >= String.length "/api/json/x/" &&
                            String.sub path 0 (String.length "/api/json/x/") = "/api/json/x/" ->
               let key=String.sub path (String.length "/api/json/x/") (String.length path - String.length "/api/json/x/") in
               handle_send_exposed_json ~key body
           | _ -> (404, "text/plain; charset=utf-8", "not found")
         in
         safe_write (http_response ~code ~content_type:ctype resp_body)
   with
   | Exit -> ()
   | _ -> ());
  (try close_in ic with _ -> ());
  (try close_out oc with _ -> ());
  (try Unix.close client with _ -> ())
  
let start ~(port:int) : unit =
  match !server_thread with
  | Some _ -> ()
  | None ->
      let thr =
        Thread.create
          (fun () ->
             let sock = Unix.socket PF_INET SOCK_STREAM 0 in
             Unix.setsockopt sock SO_REUSEADDR true;
             Unix.bind sock (ADDR_INET (Unix.inet_addr_any, port));
             Unix.listen sock 50;
             Printf.printf "[web] listening on http://localhost:%d/\n%!" port;
             while true do
               let (client, _) = Unix.accept sock in
               ignore (Thread.create handle_client client)
             done)
          ()
      in
      server_thread := Some thr
