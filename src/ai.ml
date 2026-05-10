(* Minimal HTTP wrapper to the Gemini API for the OCaml AIPL runtime.
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
(* Per-million-token pricing in USD.  Cached 2026-04 from each
   provider's rate card.  Unrecognised models contribute 0 to cost. *)

let pricing : (string, float * float) Hashtbl.t = Hashtbl.create 16
let () =
  List.iter (fun (m, ip, op) -> Hashtbl.replace pricing m (ip, op)) [
    (* Anthropic *)
    "claude-opus-4-7",        5.00,  25.00;
    "claude-opus-4-6",        5.00,  25.00;
    "claude-sonnet-4-6",      3.00,  15.00;
    "claude-haiku-4-5",       1.00,   5.00;
    (* Gemini *)
    "gemini-2.5-pro",         1.25,  10.00;
    "gemini-2.5-flash",       0.075,  0.30;
    "gemini-2.5-flash-lite",  0.10,   0.40;
    (* OpenAI *)
    "gpt-4o",                 2.50,  10.00;
    "gpt-4o-mini",            0.15,   0.60;
    "gpt-4-turbo",           10.00,  30.00;
    "o1-mini",                1.10,   4.40;
    "o3-mini",                1.10,   4.40;
  ]

let cost_for_model (model : string) (in_t : int) (out_t : int) : float =
  match Hashtbl.find_opt pricing model with
  | None -> 0.0
  | Some (ip, op) ->
      (float_of_int in_t  /. 1_000_000.0) *. ip
   +. (float_of_int out_t /. 1_000_000.0) *. op

(* ------------------------------------------------------------------ *)
(* Live counters *)

let counter_mutex = Mutex.create ()
let total_calls         = ref 0
let total_input_tokens  = ref 0
let total_output_tokens = ref 0
let total_cost_usd      = ref 0.0

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

(* Persistent counters file (optional, ABCL_AI_USAGE_FILE). *)

let usage_file_path () = Sys.getenv_opt "ABCL_AI_USAGE_FILE"

let read_int_field path field default =
  let cmd = Printf.sprintf "jq -r '.%s // %d' %s 2>/dev/null"
    field default (Filename.quote path) in
  let ic = Unix.open_process_in cmd in
  let buf = Buffer.create 32 in
  (try while true do Buffer.add_channel buf ic 32 done
   with End_of_file -> ());
  let _ = Unix.close_process_in ic in
  let s = String.trim (Buffer.contents buf) in
  try int_of_string s with _ -> default

let read_float_field path field default =
  let cmd = Printf.sprintf "jq -r '.%s // %g' %s 2>/dev/null"
    field default (Filename.quote path) in
  let ic = Unix.open_process_in cmd in
  let buf = Buffer.create 32 in
  (try while true do Buffer.add_channel buf ic 32 done
   with End_of_file -> ());
  let _ = Unix.close_process_in ic in
  let s = String.trim (Buffer.contents buf) in
  try float_of_string s with _ -> default

let load_persistent_usage () =
  match usage_file_path () with
  | Some p when Sys.file_exists p ->
      let calls = read_int_field   p "calls" 0 in
      let in_t  = read_int_field   p "input_tokens" 0 in
      let out_t = read_int_field   p "output_tokens" 0 in
      let cost  = read_float_field p "cost_usd" 0.0 in
      Mutex.lock counter_mutex;
      total_calls         := calls;
      total_input_tokens  := in_t;
      total_output_tokens := out_t;
      total_cost_usd      := cost;
      Mutex.unlock counter_mutex
  | _ -> ()

let save_persistent_usage_locked () =
  match usage_file_path () with
  | None -> ()
  | Some p ->
      let body =
        Printf.sprintf
          {|{"calls":%d,"input_tokens":%d,"output_tokens":%d,"cost_usd":%.10f}|}
          !total_calls !total_input_tokens !total_output_tokens
          !total_cost_usd
      in
      let dir = Filename.dirname p in
      let dir = if dir = "" then "." else dir in
      (try Unix.mkdir dir 0o755 with _ -> ());
      let tmp = Filename.temp_file ~temp_dir:dir ".usage_" "" in
      let oc = open_out tmp in
      output_string oc body;
      close_out oc;
      (try Sys.rename tmp p with _ -> (try Sys.remove tmp with _ -> ()))

let () = load_persistent_usage ()

let record_usage ?(model="") (in_t : int) (out_t : int) : unit =
  let cost = if model = "" then 0.0 else cost_for_model model in_t out_t in
  Mutex.lock counter_mutex;
  incr total_calls;
  total_input_tokens  := !total_input_tokens  + in_t;
  total_output_tokens := !total_output_tokens + out_t;
  total_cost_usd      := !total_cost_usd      +. cost;
  save_persistent_usage_locked ();
  Mutex.unlock counter_mutex

let get_cost_usd () : float =
  Mutex.lock counter_mutex;
  let c = !total_cost_usd in
  Mutex.unlock counter_mutex;
  c

let get_usage_string () : string =
  Mutex.lock counter_mutex;
  let s =
    Printf.sprintf "calls=%d in=%d out=%d total=%d cost=$%.6f"
      !total_calls !total_input_tokens !total_output_tokens
      (!total_input_tokens + !total_output_tokens) !total_cost_usd
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

let default_anthropic_model = "claude-opus-4-7"
let default_openai_model    = "gpt-4o-mini"

type provider = Gemini | Anthropic | OpenAI | Mock

let select_provider () : provider =
  match Sys.getenv_opt "ABCL_AI_PROVIDER" with
  | Some s ->
      (match String.lowercase_ascii (String.trim s) with
       | "anthropic" -> Anthropic
       | "openai"    -> OpenAI
       | "gemini"    -> Gemini
       | "mock"      -> Mock
       | other -> failwith (Printf.sprintf "Unknown ABCL_AI_PROVIDER: %s" other))
  | None ->
      if Sys.getenv_opt "GEMINI_API_KEY"    <> None then Gemini
      else if Sys.getenv_opt "ANTHROPIC_API_KEY" <> None then Anthropic
      else if Sys.getenv_opt "OPENAI_API_KEY"    <> None then OpenAI
      else failwith
        "ai_call: no provider key set (GEMINI_API_KEY / ANTHROPIC_API_KEY / OPENAI_API_KEY) — or ABCL_AI_PROVIDER=mock for offline tests"

(* Comma-separated fallback list; tried in order on retryable errors. *)
let fallback_models () : string list =
  match Sys.getenv_opt "ABCL_AI_FALLBACK_MODELS" with
  | None | Some "" -> []
  | Some raw ->
      String.split_on_char ',' raw
      |> List.map String.trim
      |> List.filter (fun s -> s <> "")

(* Crude retry classifier — match by substring in the exception
   message.  Mirrors the Python _is_retryable shape. *)
let str_contains haystack needle =
  let nh = String.length haystack in
  let nn = String.length needle in
  if nn = 0 || nn > nh then false
  else
    let rec walk i =
      if i + nn > nh then false
      else if String.sub haystack i nn = needle then true
      else walk (i + 1)
    in
    walk 0

let is_retryable (msg : string) : bool =
  let lower = String.lowercase_ascii msg in
  List.exists (str_contains lower) [
    "429"; "rate limit"; "rate_limit";
    "500"; "502"; "503"; "504";
    "overloaded"; "unavailable"; "deadline"; "timeout";
  ]

(* Mock provider — no network, no key.  Useful for offline smoke. *)
let do_mock_request ~system ~model:_ ~max_tokens:_ (prompt:string)
    : string * int * int =
  let head =
    let s = String.map (fun c -> if c = '\n' then ' ' else c) prompt in
    if String.length s > 60 then String.sub s 0 60 else s
  in
  let sys_tag = match system with
    | None -> ""
    | Some s ->
        let head_s = if String.length s > 18 then String.sub s 0 18 else s in
        Printf.sprintf " sys=(%s...)" head_s
  in
  let response = Printf.sprintf "[mock] reply%s for: %s" sys_tag head in
  let est_in  = max 1 (String.length prompt   / 4) in
  let est_out = max 1 (String.length response / 4) in
  (response, est_in, est_out)

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

let do_anthropic_request ~system ~model ~max_tokens (prompt:string)
    : string * int * int =
  let api_key =
    try Sys.getenv "ANTHROPIC_API_KEY"
    with Not_found -> failwith "ai_call: ANTHROPIC_API_KEY not set"
  in
  let body_buf = Buffer.create 1024 in
  Buffer.add_string body_buf "{\"model\":";
  Buffer.add_string body_buf (json_escape_string model);
  Buffer.add_string body_buf (Printf.sprintf ",\"max_tokens\":%d" max_tokens);
  Buffer.add_string body_buf ",\"messages\":[{\"role\":\"user\",\"content\":";
  Buffer.add_string body_buf (json_escape_string prompt);
  Buffer.add_string body_buf "}]";
  (match system with
   | None -> ()
   | Some s ->
       Buffer.add_string body_buf ",\"system\":";
       Buffer.add_string body_buf (json_escape_string s));
  Buffer.add_string body_buf "}";
  let body = Buffer.contents body_buf in

  let req_file  = Filename.temp_file "abcl_ai_req"  ".json" in
  let resp_file = Filename.temp_file "abcl_ai_resp" ".json" in
  let oc = open_out req_file in
  output_string oc body;
  close_out oc;

  let curl_cmd =
    Printf.sprintf
      "curl -s -X POST 'https://api.anthropic.com/v1/messages' \
       -H 'x-api-key: %s' \
       -H 'anthropic-version: 2023-06-01' \
       -H 'Content-Type: application/json' \
       -d @%s -o %s 2>/dev/null"
      (Filename.quote api_key) (Filename.quote req_file) (Filename.quote resp_file)
  in
  ignore (Sys.command curl_cmd);

  let text =
    jq_extract resp_file
      ".content[0].text // .error.message // \"<no response>\""
  in
  let in_t  = int_or_zero (jq_extract resp_file ".usage.input_tokens  // 0") in
  let out_t = int_or_zero (jq_extract resp_file ".usage.output_tokens // 0") in

  (try Sys.remove req_file  with _ -> ());
  (try Sys.remove resp_file with _ -> ());
  (text, in_t, out_t)


let do_openai_request ~system ~model ~max_tokens (prompt:string)
    : string * int * int =
  let api_key =
    try Sys.getenv "OPENAI_API_KEY"
    with Not_found -> failwith "ai_call: OPENAI_API_KEY not set"
  in
  let body_buf = Buffer.create 1024 in
  Buffer.add_string body_buf "{\"model\":";
  Buffer.add_string body_buf (json_escape_string model);
  Buffer.add_string body_buf
    (Printf.sprintf ",\"max_completion_tokens\":%d" max_tokens);
  Buffer.add_string body_buf ",\"messages\":[";
  (match system with
   | None -> ()
   | Some s ->
       Buffer.add_string body_buf "{\"role\":\"system\",\"content\":";
       Buffer.add_string body_buf (json_escape_string s);
       Buffer.add_string body_buf "},");
  Buffer.add_string body_buf "{\"role\":\"user\",\"content\":";
  Buffer.add_string body_buf (json_escape_string prompt);
  Buffer.add_string body_buf "}]}";
  let body = Buffer.contents body_buf in

  let req_file  = Filename.temp_file "abcl_ai_req"  ".json" in
  let resp_file = Filename.temp_file "abcl_ai_resp" ".json" in
  let oc = open_out req_file in
  output_string oc body;
  close_out oc;

  let curl_cmd =
    Printf.sprintf
      "curl -s -X POST 'https://api.openai.com/v1/chat/completions' \
       -H 'Authorization: Bearer %s' \
       -H 'Content-Type: application/json' \
       -d @%s -o %s 2>/dev/null"
      (Filename.quote api_key) (Filename.quote req_file) (Filename.quote resp_file)
  in
  ignore (Sys.command curl_cmd);

  let text =
    jq_extract resp_file
      ".choices[0].message.content // .error.message // \"<no response>\""
  in
  let in_t  = int_or_zero (jq_extract resp_file ".usage.prompt_tokens     // 0") in
  let out_t = int_or_zero (jq_extract resp_file ".usage.completion_tokens // 0") in

  (try Sys.remove req_file  with _ -> ());
  (try Sys.remove resp_file with _ -> ());
  (text, in_t, out_t)


let dispatch_one ~provider ~system ~model ~max_tokens prompt =
  match provider with
  | Gemini    -> do_gemini_request    ~system ~model ~max_tokens prompt
  | Anthropic -> do_anthropic_request ~system ~model ~max_tokens prompt
  | OpenAI    -> do_openai_request    ~system ~model ~max_tokens prompt
  | Mock      -> do_mock_request      ~system ~model ~max_tokens prompt

let default_for_provider p = function
  | Some m when m <> "" -> m
  | _ ->
      (match p with
       | Gemini    -> default_model
       | Anthropic -> default_anthropic_model
       | OpenAI    -> default_openai_model
       | Mock      -> "mock")

let call_gemini ?(system : string option = None) ?(model : string = "")
                ?(max_tokens : int = default_max_tokens) (prompt : string) : string =
  check_budget ();
  let sem = get_concurrency_sem () in
  (match sem with Some s -> Sem.acquire s | None -> ());
  let result_or_exn =
    try
      let p = select_provider () in
      let primary = default_for_provider p (Some model) in
      let chain = primary :: List.filter (fun m -> m <> primary) (fallback_models ()) in
      let rec try_chain ms last_err =
        match ms with
        | [] -> (match last_err with Some e -> raise e | None -> failwith "no models")
        | m :: rest ->
            (try Ok (dispatch_one ~provider:p ~system ~model:m ~max_tokens prompt)
             with e ->
               if rest = [] || not (is_retryable (Printexc.to_string e))
               then raise e
               else begin
                 let delay = 0.5 *. (2.0 ** float_of_int (List.length chain - List.length rest - 1)) in
                 Printf.eprintf "[ai_fallback] %s failed (%s); retry %s after %.2fs\n%!"
                   m (Printexc.to_string e) (List.hd rest) delay;
                 Thread.delay (delay +. Random.float 0.25);
                 try_chain rest (Some e)
               end)
      in
      (match try_chain chain None with
       | Ok r -> Ok r
       | _ -> failwith "unreachable")
    with e -> Error e
  in
  (match sem with Some s -> Sem.release s | None -> ());
  match result_or_exn with
  | Error e -> raise e
  | Ok (text, in_t, out_t) ->
      let model_used = default_for_provider (select_provider ()) (Some model) in
      record_usage ~model:model_used in_t out_t;
      text

(* Same-model retry (different from fallback chain which switches
   models).  Used by the ai_call_retry primitive. *)
let call_with_retry ?(system : string option = None) ?(model : string = "")
                    ?(max_tokens : int = default_max_tokens)
                    ~(max_attempts : int) (prompt : string) : string =
  let last_err = ref None in
  let result = ref None in
  let n = max 1 max_attempts in
  let i = ref 0 in
  while !result = None && !i < n do
    (try
      result := Some (call_gemini ~system ~model ~max_tokens prompt)
    with e ->
      last_err := Some e;
      let retryable = is_retryable (Printexc.to_string e) in
      if !i < n - 1 && retryable then begin
        let delay = 0.5 *. (2.0 ** float_of_int !i) +. Random.float 0.25 in
        Printf.eprintf "[ai_retry] attempt %d/%d failed (%s); retry in %.2fs\n%!"
          (!i + 1) n (Printexc.to_string e) delay;
        Thread.delay delay
      end else
        raise e);
    incr i
  done;
  match !result with
  | Some t -> t
  | None ->
      (match !last_err with
       | Some e -> raise e
       | None -> failwith "no result")
