(* Minimal HTTP wrapper to the Gemini API for the OCaml ABCL/c+ runtime.
   Shells out to curl (handles TLS) and jq (extracts the response text)
   so we don't pull in any new opam dependencies for this first cut.

   Required env var: GEMINI_API_KEY
   Default model:    gemini-2.5-flash *)

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

let default_model = "gemini-2.5-flash"
let default_max_tokens = 4096

let call_gemini ?(system : string option = None) ?(model : string = default_model)
                ?(max_tokens : int = default_max_tokens) (prompt : string) : string =
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

  let req_file = Filename.temp_file "abcl_ai_req" ".json" in
  let oc = open_out req_file in
  output_string oc body;
  close_out oc;

  let url =
    Printf.sprintf
      "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent?key=%s"
      model api_key
  in
  let cmd =
    Printf.sprintf
      "curl -s -X POST %s -H 'Content-Type: application/json' -d @%s | jq -r '.candidates[0].content.parts[0].text // .error.message // \"<no response>\"'"
      (Filename.quote url) (Filename.quote req_file)
  in
  let ic = Unix.open_process_in cmd in
  let response = read_all ic in
  let _ = Unix.close_process_in ic in
  (try Sys.remove req_file with _ -> ());

  (* Trim trailing newline that jq always appends. *)
  let n = String.length response in
  if n > 0 && response.[n - 1] = '\n' then String.sub response 0 (n - 1)
  else response
