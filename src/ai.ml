(* Minimal HTTP wrapper to the Gemini API for the OCaml ABCL/c+ runtime.
   Shells out to curl (handles TLS) and jq (extracts response fields).

   Required env var: GEMINI_API_KEY
   Default model:    gemini-2.5-flash

   AI-OS governance knobs (env vars, all optional):

     ABCL_AI_TOKEN_BUDGET=N   total prompt+completion tokens cap; calls
                              past the cap raise Budget_exceeded
     ABCL_AI_MAX_CONCURRENT=N at most N AI calls in flight at once;
                              excess actors block on a semaphore (FIFO)
*)

exception Budget_exceeded of string

(* ------------------------------------------------------------------ *)
(* Tiny counting semaphore.  OCaml 4.x stdlib has no Semaphore, so we
   roll a 20-line one out of Mutex + Condition. *)

module Sem = struct
  type t = {
    mutex : Mutex.t;
    cond  : Condition.t;
    mutable available : int;
  }

  let create n =
    { mutex = Mutex.create (); cond = Condition.create (); available = n }

  let acquire t =
    Mutex.lock t.mutex;
    while t.available <= 0 do Condition.wait t.cond t.mutex done;
    t.available <- t.available - 1;
    Mutex.unlock t.mutex

  let release t =
    Mutex.lock t.mutex;
    t.available <- t.available + 1;
    Condition.signal t.cond;
    Mutex.unlock t.mutex
end

(* ------------------------------------------------------------------ *)
(* Live counters *)

let counter_mutex = Mutex.create ()
let total_calls         = ref 0
let total_input_tokens  = ref 0
let total_output_tokens = ref 0

let int_env (name : string) (default : int) : int =
  try
    let raw = String.trim (Sys.getenv name) in
    if raw = "" then default else int_of_string raw
  with Not_found -> default
     | Failure _  -> default

let get_budget () = int_env "ABCL_AI_TOKEN_BUDGET" 0

let check_budget () =
  let budget = get_budget () in
  if budget <= 0 then ()
  else begin
    Mutex.lock counter_mutex;
    let used = !total_input_tokens + !total_output_tokens in
    Mutex.unlock counter_mutex;
    if used >= budget then
      raise (Budget_exceeded
        (Printf.sprintf "AI token budget exceeded: used=%d budget=%d" used budget))
  end

let record_usage (in_t : int) (out_t : int) : unit =
  Mutex.lock counter_mutex;
  incr total_calls;
  total_input_tokens  := !total_input_tokens  + in_t;
  total_output_tokens := !total_output_tokens + out_t;
  Mutex.unlock counter_mutex

let get_usage_string () : string =
  Mutex.lock counter_mutex;
  let s =
    Printf.sprintf "calls=%d in=%d out=%d total=%d"
      !total_calls !total_input_tokens !total_output_tokens
      (!total_input_tokens + !total_output_tokens)
  in
  Mutex.unlock counter_mutex;
  s

let get_remaining () : int =
  let budget = get_budget () in
  if budget <= 0 then -1
  else begin
    Mutex.lock counter_mutex;
    let used = !total_input_tokens + !total_output_tokens in
    Mutex.unlock counter_mutex;
    max 0 (budget - used)
  end

(* Lazy concurrency semaphore *)
let concurrency_init_mutex = Mutex.create ()
let concurrency_sem : Sem.t option ref = ref None
let concurrency_inited = ref false

let get_concurrency_sem () : Sem.t option =
  if !concurrency_inited then !concurrency_sem
  else begin
    Mutex.lock concurrency_init_mutex;
    if not !concurrency_inited then begin
      let limit = int_env "ABCL_AI_MAX_CONCURRENT" 0 in
      concurrency_sem :=
        (if limit > 0 then Some (Sem.create limit) else None);
      concurrency_inited := true
    end;
    Mutex.unlock concurrency_init_mutex;
    !concurrency_sem
  end

(* ------------------------------------------------------------------ *)
(* Helpers *)

let json_escape_string (s : string) : string =
  let buf = Buffer.create (String.length s + 2) in
  Buffer.add_char buf '"';
  String.iter (fun c ->
    match c with
    | '"' -> Buffer.add_string buf "\\\""
    | '\\' -> Buffer.add_string buf "\\\\"
    | '\n' -> Buffer.add_string buf "\\n"
    | '\r' -> Buffer.add_string buf "\\r"
    | '\t' -> Buffer.add_string buf "\\t"
    | c when Char.code c < 0x20 ->
        Buffer.add_string buf (Printf.sprintf "\\u%04x" (Char.code c))
    | c -> Buffer.add_char buf c
  ) s;
  Buffer.add_char buf '"';
  Buffer.contents buf

let read_all (ic : in_channel) : string =
  let buf = Buffer.create 4096 in
  (try
    while true do
      Buffer.add_channel buf ic 4096
    done
  with End_of_file -> ());
  Buffer.contents buf

let trim_trailing_newline (s : string) : string =
  let n = String.length s in
  if n > 0 && s.[n - 1] = '\n' then String.sub s 0 (n - 1) else s

let jq_extract (resp_file : string) (query : string) : string =
  let cmd =
    Printf.sprintf "jq -r %s %s 2>/dev/null"
      (Filename.quote query) (Filename.quote resp_file)
  in
  let ic = Unix.open_process_in cmd in
  let s = read_all ic in
  let _ = Unix.close_process_in ic in
  trim_trailing_newline s

let int_or_zero (s : string) : int =
  try int_of_string (String.trim s) with _ -> 0

(* ------------------------------------------------------------------ *)
(* Public entry points *)

let default_model = "gemini-2.5-flash"
let default_max_tokens = 4096

let do_gemini_request ~system ~model ~max_tokens (prompt : string)
    : string * int * int =
  let api_key =
    try Sys.getenv "GEMINI_API_KEY"
    with Not_found -> failwith "ai_call: GEMINI_API_KEY environment variable not set"
  in

  let body_buf = Buffer.create 1024 in
  Buffer.add_string body_buf "{\"contents\":[{\"parts\":[{\"text\":";
  Buffer.add_string body_buf (json_escape_string prompt);
  Buffer.add_string body_buf "}]}]";
  Buffer.add_string body_buf
    (Printf.sprintf ",\"generationConfig\":{\"maxOutputTokens\":%d}" max_tokens);
  (match system with
   | None -> ()
   | Some sys ->
       Buffer.add_string body_buf ",\"systemInstruction\":{\"parts\":[{\"text\":";
       Buffer.add_string body_buf (json_escape_string sys);
       Buffer.add_string body_buf "}]}");
  Buffer.add_string body_buf "}";
  let body = Buffer.contents body_buf in

  let req_file  = Filename.temp_file "abcl_ai_req"  ".json" in
  let resp_file = Filename.temp_file "abcl_ai_resp" ".json" in
  let oc = open_out req_file in
  output_string oc body;
  close_out oc;

  let url =
    Printf.sprintf
      "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent?key=%s"
      model api_key
  in
  let curl_cmd =
    Printf.sprintf
      "curl -s -X POST %s -H 'Content-Type: application/json' -d @%s -o %s 2>/dev/null"
      (Filename.quote url) (Filename.quote req_file) (Filename.quote resp_file)
  in
  ignore (Sys.command curl_cmd);

  let text =
    jq_extract resp_file
      ".candidates[0].content.parts[0].text // .error.message // \"<no response>\""
  in
  let in_t  = int_or_zero (jq_extract resp_file ".usageMetadata.promptTokenCount // 0") in
  let out_t = int_or_zero (jq_extract resp_file ".usageMetadata.candidatesTokenCount // 0") in

  (try Sys.remove req_file  with _ -> ());
  (try Sys.remove resp_file with _ -> ());

  (text, in_t, out_t)

let call_gemini ?(system : string option = None) ?(model : string = default_model)
                ?(max_tokens : int = default_max_tokens) (prompt : string) : string =
  check_budget ();
  let sem = get_concurrency_sem () in
  (match sem with Some s -> Sem.acquire s | None -> ());
  let result_or_exn =
    try Ok (do_gemini_request ~system ~model ~max_tokens prompt)
    with e -> Error e
  in
  (match sem with Some s -> Sem.release s | None -> ());
  match result_or_exn with
  | Error e -> raise e
  | Ok (text, in_t, out_t) ->
      record_usage in_t out_t;
      text
