(* tui_ide.ml — Terminal UI for AIPL.
   Native OCaml alternative to the web-based IDE. Connects to a running
   repl_thread.exe via the existing HTTP gateway and draws a multi-pane
   terminal UI.

   Layout (dynamically sized to terminal):
     +------------------------------------------------------------+
     | [header]                                                   |
     +--------------------------+---------------------------------+
     | Output pane              | Actors pane                     |
     |                          |                                 |
     +--------------------------+                                 |
     | Source pane              |                                 |
     |                          |                                 |
     +--------------------------+---------------------------------+
     | AIPL> _ input                                            |
     +------------------------------------------------------------+
*)

open Unix

(* ================================================================== *)
(*                          HTTP client                                *)
(* ================================================================== *)

let read_all_sock (s:file_descr) : string =
  let buf = Bytes.create 8192 in
  let out = Buffer.create 8192 in
  let rec loop () =
    try
      let n = read s buf 0 (Bytes.length buf) in
      if n > 0 then (Buffer.add_subbytes out buf 0 n; loop ())
    with Unix_error _ -> ()
  in
  loop ();
  Buffer.contents out

let split_http (raw:string) : int * string =
  let n = String.length raw in
  let sep = "\r\n\r\n" in
  let slen = String.length sep in
  let rec find i =
    if i + slen > n then -1
    else if String.sub raw i slen = sep then i
    else find (i + 1)
  in
  let body_start = find 0 in
  let body =
    if body_start < 0 then ""
    else String.sub raw (body_start + slen) (n - body_start - slen)
  in
  let status =
    try
      let line_end = String.index raw '\n' in
      let line = String.sub raw 0 line_end in
      match String.split_on_char ' ' line with
      | _ :: code :: _ -> int_of_string (String.trim code)
      | _ -> 0
    with _ -> 0
  in
  (status, body)

let http_request ~meth ~host ~port ~path ?(body="") () : int * string =
  let s = socket PF_INET SOCK_STREAM 0 in
  let addr = ADDR_INET (inet_addr_of_string host, port) in
  (try connect s addr with e -> (try close s with _ -> ()); raise e);
  let req =
    if meth = "GET" then
      Printf.sprintf
        "GET %s HTTP/1.1\r\nHost: %s:%d\r\nConnection: close\r\n\r\n"
        path host port
    else
      Printf.sprintf
        "POST %s HTTP/1.1\r\nHost: %s:%d\r\nContent-Type: application/json\r\nContent-Length: %d\r\nConnection: close\r\n\r\n%s"
        path host port (String.length body) body
  in
  let _ = write_substring s req 0 (String.length req) in
  let raw = read_all_sock s in
  (try close s with _ -> ());
  split_http raw

(* ================================================================== *)
(*                          Minimal JSON parser                        *)
(* ================================================================== *)

type jv =
  | JNull
  | JBool of bool
  | JNumber of float
  | JString of string
  | JArray of jv list
  | JObject of (string * jv) list

exception Json_err of string

let parse_json (s:string) : jv =
  let n = String.length s in
  let i = ref 0 in
  let is_ws c = c = ' ' || c = '\t' || c = '\n' || c = '\r' in
  let skip_ws () = while !i < n && is_ws s.[!i] do incr i done in
  let peek () = if !i < n then Some s.[!i] else None in
  let next () = let c = peek () in incr i; c in
  let expect ch =
    skip_ws ();
    match next () with
    | Some c when c = ch -> ()
    | _ -> raise (Json_err (Printf.sprintf "expected '%c'" ch))
  in
  let rec parse_string () : string =
    expect '"';
    let b = Buffer.create 32 in
    let rec loop () =
      match next () with
      | None -> raise (Json_err "unterminated string")
      | Some '"' -> Buffer.contents b
      | Some '\\' ->
          (match next () with
           | Some 'n' -> Buffer.add_char b '\n'
           | Some 'r' -> Buffer.add_char b '\r'
           | Some 't' -> Buffer.add_char b '\t'
           | Some '"' -> Buffer.add_char b '"'
           | Some '\\' -> Buffer.add_char b '\\'
           | Some '/' -> Buffer.add_char b '/'
           | Some c -> Buffer.add_char b c
           | None -> raise (Json_err "bad escape"));
          loop ()
      | Some c -> Buffer.add_char b c; loop ()
    in loop ()
  in
  let parse_number () =
    skip_ws ();
    let start = !i in
    while !i < n && (match s.[!i] with
      | '0'..'9' | '-' | '+' | '.' | 'e' | 'E' -> true
      | _ -> false) do incr i done;
    try float_of_string (String.sub s start (!i - start))
    with _ -> raise (Json_err "bad number")
  in
  let rec parse_value () : jv =
    skip_ws ();
    match peek () with
    | None -> raise (Json_err "unexpected EOF")
    | Some '{' -> parse_object ()
    | Some '[' -> parse_array ()
    | Some '"' -> JString (parse_string ())
    | Some 't' -> i := !i + 4; JBool true
    | Some 'f' -> i := !i + 5; JBool false
    | Some 'n' -> i := !i + 4; JNull
    | Some _ -> JNumber (parse_number ())
  and parse_array () =
    expect '[';
    skip_ws ();
    let items = ref [] in
    (match peek () with
     | Some ']' -> incr i
     | _ ->
         items := [parse_value ()];
         let rec loop () =
           skip_ws ();
           match peek () with
           | Some ',' -> incr i; items := parse_value () :: !items; loop ()
           | Some ']' -> incr i
           | _ -> raise (Json_err "expected , or ]")
         in loop ());
    JArray (List.rev !items)
  and parse_object () =
    expect '{';
    skip_ws ();
    let items = ref [] in
    (match peek () with
     | Some '}' -> incr i
     | _ ->
         let parse_kv () =
           skip_ws ();
           let k = parse_string () in
           skip_ws (); expect ':';
           let v = parse_value () in
           items := (k, v) :: !items
         in
         parse_kv ();
         let rec loop () =
           skip_ws ();
           match peek () with
           | Some ',' -> incr i; parse_kv (); loop ()
           | Some '}' -> incr i
           | _ -> raise (Json_err "expected , or }")
         in loop ());
    JObject (List.rev !items)
  in
  parse_value ()

let jget j k =
  match j with
  | JObject kvs -> List.assoc_opt k kvs
  | _ -> None

let jget_string j k =
  match jget j k with Some (JString s) -> s | _ -> ""

let jget_int j k =
  match jget j k with Some (JNumber f) -> int_of_float f | _ -> 0

let json_esc_str s =
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

(* ================================================================== *)
(*                             Terminal                                *)
(* ================================================================== *)

let esc = "\027["

let obuf = Buffer.create 8192
let put s = Buffer.add_string obuf s
let putf fmt = Printf.ksprintf put fmt
let flush_screen () =
  print_string (Buffer.contents obuf);
  Buffer.clear obuf;
  flush Stdlib.stdout

let clear_screen () = put (esc ^ "2J" ^ esc ^ "H")
let hide_cursor ()  = put (esc ^ "?25l")
let show_cursor ()  = put (esc ^ "?25h")
let goto r c        = putf "%s%d;%dH" esc r c
let reset ()        = put (esc ^ "0m")
let bold ()         = put (esc ^ "1m")
let dim ()          = put (esc ^ "2m")
let fg r g b        = putf "%s38;2;%d;%d;%dm" esc r g b
let bg r g b        = putf "%s48;2;%d;%d;%dm" esc r g b

(* Terminal size *)
let term_rows = ref 40
let term_cols = ref 120

let refresh_term_size () =
  try
    let ic = Unix.open_process_in "stty size 2>/dev/null" in
    let line = input_line ic in
    let _ = Unix.close_process_in ic in
    match String.split_on_char ' ' line with
    | [r; c] ->
        let r' = int_of_string r in
        let c' = int_of_string c in
        if r' > 10 && c' > 40 then begin
          term_rows := r';
          term_cols := c'
        end
    | _ -> ()
  with _ -> ()

let enter_raw () =
  let _ = Sys.command "stty -icanon -echo min 0 time 1 2>/dev/null" in
  ()

let leave_raw () =
  show_cursor ();
  reset ();
  clear_screen ();
  flush_screen ();
  let _ = Sys.command "stty sane 2>/dev/null" in
  ()

(* Truncate / pad helpers.
   NOTE: we treat OCaml's String.length as an approximation of visible width.
   Non-ASCII (multi-byte) characters will skew this, but most of our text is
   ASCII so it's close enough for a basic TUI. *)
let trunc s w =
  if w <= 0 then ""
  else if String.length s <= w then s
  else if w = 1 then String.sub s 0 1
  else String.sub s 0 (w - 1) ^ "…"

let pad s w =
  let s = trunc s w in
  let pad_n = max 0 (w - String.length s) in
  s ^ String.make pad_n ' '

(* ================================================================== *)
(*                            App state                                *)
(* ================================================================== *)

let host = ref "127.0.0.1"
let port = ref 8080

let max_output_lines = 400
let output_lines : string Queue.t = Queue.create ()

let add_output_text (s:string) =
  if s <> "" then begin
    let lines = String.split_on_char '\n' s in
    List.iter (fun l ->
      (* strip trailing \r *)
      let l =
        let n = String.length l in
        if n > 0 && l.[n-1] = '\r' then String.sub l 0 (n-1) else l
      in
      Queue.add l output_lines
    ) lines;
    while Queue.length output_lines > max_output_lines do
      ignore (Queue.pop output_lines)
    done
  end

type actor_info = {
  a_name    : string;
  a_class   : string;
  a_type    : string;
  a_mbox    : int;
  a_methods : string list;
}

let actors : actor_info list ref = ref []
let selected_actor : string option ref = ref None
let source_text = ref "(アクタを選択して 'select <name>' or 'pprint <name>')"
let actors_scroll = ref 0    (* vertical offset inside actors pane *)
let output_scroll = ref 0    (* 0 = follow tail; >0 lines from bottom *)
let source_scroll = ref 0
let status_msg = ref ""
let dirty = ref true
let quit_requested = ref false

(* Input buffer *)
let input_buf = Buffer.create 256
let input_cursor = ref 0

let input_string () = Buffer.contents input_buf

let set_input s =
  Buffer.clear input_buf;
  Buffer.add_string input_buf s;
  input_cursor := String.length s

(* Command history *)
let history : string array = Array.make 100 ""
let history_count = ref 0
let history_pos   = ref (-1)  (* -1: typing a fresh line *)

let push_history cmd =
  let cmd = String.trim cmd in
  if cmd = "" then ()
  else if !history_count > 0 && history.(!history_count - 1) = cmd then ()
  else if !history_count < Array.length history then begin
    history.(!history_count) <- cmd;
    incr history_count
  end else begin
    Array.blit history 1 history 0 (Array.length history - 1);
    history.(Array.length history - 1) <- cmd
  end

(* ================================================================== *)
(*                        REPL communication                           *)
(* ================================================================== *)

let mark_status s = status_msg := s; dirty := true

let ping_server () : bool =
  try
    let (code, _) = http_request ~meth:"GET" ~host:!host ~port:!port ~path:"/api/actors" () in
    code = 200
  with _ -> false

let fetch_actors () =
  try
    let (code, body) = http_request ~meth:"GET" ~host:!host ~port:!port ~path:"/api/actors" () in
    if code = 200 then begin
      let j = parse_json body in
      match j with
      | JArray xs ->
          actors := List.map (fun o ->
            let methods =
              match o with
              | JObject kvs ->
                  (match List.assoc_opt "methods" kvs with
                   | Some (JArray ms) ->
                       List.filter_map (function JString s -> Some s | _ -> None) ms
                   | _ -> [])
              | _ -> []
            in
            {
              a_name    = jget_string o "name";
              a_class   = jget_string o "class";
              a_type    = jget_string o "type";
              a_mbox    = jget_int    o "mbox";
              a_methods = methods;
            }
          ) xs;
          dirty := true
      | _ -> ()
    end
  with _ -> ()

let send_repl_command (cmd:string) : string =
  let body = Printf.sprintf {|{"command":"%s","sid":"tui"}|} (json_esc_str cmd) in
  try
    let (_code, out) = http_request ~meth:"POST" ~host:!host ~port:!port ~path:"/api/repl" ~body () in
    out
  with e ->
    "[http error] " ^ Printexc.to_string e

let refresh_source () =
  match !selected_actor with
  | None ->
      source_text := "(アクタ未選択: 'select <name>' で指定)";
      dirty := true
  | Some name ->
      let out = send_repl_command ("pprint " ^ name) in
      let s = String.trim out in
      source_text :=
        (if s = "" || s = "OK" then "(ソースが取得できませんでした)" else out);
      dirty := true

(* ================================================================== *)
(*                              Drawing                                *)
(* ================================================================== *)

(* Color palette *)
let c_bar_bg   = (45, 45, 48)
let c_accent   = (79, 195, 247)
let c_accent2  = (255, 202, 40)
let c_fg       = (212, 212, 212)
let c_muted    = (158, 158, 158)
let c_err      = (239, 83, 80)
let c_ok       = (139, 195, 74)

let rgb (r,g,b) = fg r g b
let rgb_bg (r,g,b) = bg r g b

let draw_header () =
  goto 1 1;
  rgb_bg c_bar_bg;
  rgb c_accent;
  bold ();
  let sel = match !selected_actor with Some a -> "sel=" ^ a | None -> "sel=(none)" in
  let left  = Printf.sprintf " AIPL TUI IDE | actors=%d | %s" (List.length !actors) sel in
  let right = " F1:help F2:compile F5:refresh F10:quit " in
  let pad_n = max 1 (!term_cols - String.length left - String.length right) in
  put (left ^ String.make pad_n ' ' ^ right);
  reset ()

let draw_status row =
  goto row 1;
  rgb_bg c_bar_bg;
  rgb c_muted;
  let s =
    if !status_msg = "" then
      Printf.sprintf " type command + Enter  (Ctrl-D to quit) | host=%s:%d " !host !port
    else
      " " ^ !status_msg ^ " "
  in
  put (pad s !term_cols);
  reset ()

(* Draw a bordered pane with a title. Returns the inner (r,c,h,w). *)
let draw_pane ~r ~c ~h ~w ~title : int * int * int * int =
  (* top *)
  goto r c;
  rgb c_muted;
  put "┌";
  for _=1 to w - 2 do put "─" done;
  put "┐";
  (* title overlay *)
  if title <> "" then begin
    goto r (c + 2);
    rgb c_accent; bold ();
    put ("┤ " ^ trunc title (w - 6) ^ " ├");
    reset (); rgb c_muted
  end;
  (* sides *)
  for i = 1 to h - 2 do
    goto (r + i) c; put "│";
    goto (r + i) (c + w - 1); put "│"
  done;
  (* bottom *)
  goto (r + h - 1) c;
  put "└";
  for _=1 to w - 2 do put "─" done;
  put "┘";
  reset ();
  (r + 1, c + 1, h - 2, w - 2)

(* Wrap/clip a line into a given width and print it *)
let put_in_pane ~r ~c ~w text =
  goto r c;
  put (pad text w)

let draw_output_pane ~r ~c ~h ~w =
  let (ir, ic, ih, iw) = draw_pane ~r ~c ~h ~w ~title:"Output" in
  let all = Queue.fold (fun acc l -> l :: acc) [] output_lines |> List.rev in
  let n = List.length all in
  let visible = ih in
  let offset = min !output_scroll (max 0 (n - visible)) in
  (* Take tail with offset: lines[n - visible - offset ... n - offset] *)
  let start = max 0 (n - visible - offset) in
  let stop  = n - offset in
  let shown =
    List.filteri (fun i _ -> i >= start && i < stop) all
  in
  let row = ref ir in
  List.iter (fun line ->
    if !row < ir + ih then begin
      let color_line s =
        if String.length s >= 9 && String.sub s 0 9 = "AIPL> " then (rgb c_accent; bold ())
        else if String.length s >= 1 && s.[0] = '[' then begin
          let low = String.lowercase_ascii s in
          if String.length low >= 7 && String.sub low 0 7 = "[error]" then rgb c_err
          else if String.length low >= 8 && String.sub low 0 8 = "[failed]" then rgb c_err
          else if String.length low >= 7 && String.sub low 0 7 = "[reply]" then rgb c_ok
          else rgb c_muted
        end else rgb c_fg
      in
      color_line line;
      put_in_pane ~r:!row ~c:ic ~w:iw line;
      reset ();
      incr row
    end
  ) shown;
  while !row < ir + ih do
    put_in_pane ~r:!row ~c:ic ~w:iw "";
    incr row
  done

let draw_actors_pane ~r ~c ~h ~w =
  let (ir, ic, ih, iw) = draw_pane ~r ~c ~h ~w ~title:"Current Actors" in
  let list = !actors in
  if list = [] then begin
    rgb c_muted;
    put_in_pane ~r:ir ~c:ic ~w:iw "(まだアクタが登録されていません)";
    reset ();
    for i = 1 to ih - 1 do
      put_in_pane ~r:(ir + i) ~c:ic ~w:iw ""
    done
  end else begin
    let rows_per = 3 in   (* 3 lines per actor: name, type, methods *)
    let max_show = ih / rows_per in
    let offset   = min !actors_scroll (max 0 (List.length list - max_show)) in
    let shown    = List.filteri (fun i _ -> i >= offset && i < offset + max_show) list in
    let row = ref ir in
    List.iter (fun a ->
      if !row + rows_per - 1 < ir + ih then begin
        let selected = (Some a.a_name = !selected_actor) in
        if selected then (rgb_bg (9,71,113); rgb c_accent2; bold ())
        else (rgb c_accent2; bold ());
        let prefix = if selected then "▶ " else "  " in
        put_in_pane ~r:!row ~c:ic ~w:iw
          (prefix ^ a.a_name ^ " : " ^ a.a_class);
        reset ();
        incr row;
        rgb c_muted;
        let meta = Printf.sprintf "    mbox=%d   %s"
          a.a_mbox
          (if a.a_methods = [] then "(no methods)"
           else "methods: " ^ String.concat ", " a.a_methods)
        in
        put_in_pane ~r:!row ~c:ic ~w:iw meta;
        reset ();
        incr row;
        dim ();
        put_in_pane ~r:!row ~c:ic ~w:iw ("    " ^ a.a_type);
        reset ();
        incr row
      end
    ) shown;
    while !row < ir + ih do
      put_in_pane ~r:!row ~c:ic ~w:iw "";
      incr row
    done
  end

let draw_source_pane ~r ~c ~h ~w =
  let title = match !selected_actor with
    | Some n -> "Source: " ^ n
    | None -> "Source"
  in
  let (ir, ic, ih, iw) = draw_pane ~r ~c ~h ~w ~title in
  let lines = String.split_on_char '\n' !source_text in
  let n = List.length lines in
  let offset = min !source_scroll (max 0 (n - ih)) in
  let row = ref ir in
  let skipped = ref 0 in
  List.iter (fun l ->
    if !skipped < offset then incr skipped
    else if !row < ir + ih then begin
      rgb c_fg;
      put_in_pane ~r:!row ~c:ic ~w:iw l;
      reset ();
      incr row
    end
  ) lines;
  while !row < ir + ih do
    put_in_pane ~r:!row ~c:ic ~w:iw "";
    incr row
  done

let draw_input_pane row =
  goto row 1;
  rgb_bg c_bar_bg;
  rgb c_accent;
  bold ();
  put " AIPL> ";
  reset ();
  rgb_bg c_bar_bg;
  rgb c_fg;
  let prompt_w = 10 in
  let avail = !term_cols - prompt_w in
  let s = input_string () in
  let start =
    if !input_cursor >= avail then !input_cursor - avail + 1 else 0
  in
  let visible =
    let n = String.length s in
    if start >= n then "" else String.sub s start (min (n - start) avail)
  in
  put (pad visible avail);
  reset ()

let draw_all () =
  refresh_term_size ();
  Buffer.clear obuf;
  hide_cursor ();
  clear_screen ();
  draw_header ();
  (* split: header(1) + panes + status(1) + input(1) *)
  let header_rows = 1 in
  let footer_rows = 2 in
  let body_top = header_rows + 1 in
  let body_h   = !term_rows - header_rows - footer_rows in
  if body_h < 6 then begin
    goto body_top 1;
    rgb c_err;
    put "Terminal is too small.";
    reset ();
    flush_screen ();
  end else begin
    let left_w  = max 40 (!term_cols * 3 / 5) in
    let right_w = !term_cols - left_w in
    let out_h = max 6 (body_h * 3 / 5) in
    let src_h = body_h - out_h in
    draw_output_pane ~r:body_top ~c:1 ~h:out_h ~w:left_w;
    draw_source_pane ~r:(body_top + out_h) ~c:1 ~h:src_h ~w:left_w;
    draw_actors_pane ~r:body_top ~c:(left_w + 1) ~h:body_h ~w:right_w;
    draw_status (!term_rows - 1);
    draw_input_pane !term_rows;
    (* place cursor in input line *)
    let cx = 10 + min !input_cursor (!term_cols - 11) + 1 in
    goto !term_rows cx;
    show_cursor ();
    flush_screen ()
  end

(* ================================================================== *)
(*                        Command dispatch                             *)
(* ================================================================== *)

let is_local_command line =
  let l = String.trim line in
  if l = "" then false
  else
    let starts p = String.length l >= String.length p
                   && String.sub l 0 (String.length p) = p in
    l = "quit" || l = "exit"
    || l = "refresh" || l = "clear"
    || l = "?" || l = "help-tui"
    || starts "select "

let do_help_tui () =
  add_output_text
    ("[TUI help]\n"
     ^ "  help            - show REPL-side help\n"
     ^ "  help-tui / ?    - this message\n"
     ^ "  load <file>     - load .abcl source\n"
     ^ "  script <file>   - run .bat commands file\n"
     ^ "  compile         - instantiate actors\n"
     ^ "  list / actors   - refresh actor list\n"
     ^ "  send obj.m(x)   - send a message\n"
     ^ "  pprint <name>   - show source in source pane\n"
     ^ "  select <name>   - choose actor for source pane (TUI)\n"
     ^ "  refresh         - redraw + refetch actors (TUI)\n"
     ^ "  clear           - clear output (TUI)\n"
     ^ "  quit / exit     - leave TUI\n"
     ^ "Keys: Enter=send  Backspace=erase  ←/→=cursor  ↑/↓=history\n"
     ^ "      PageUp/PageDown=scroll output  Ctrl-D=quit")

let dispatch_command line =
  let l = String.trim line in
  if l = "" then ()
  else if l = "quit" || l = "exit" then begin
    add_output_text "[tui] quitting";
    quit_requested := true
  end
  else if l = "refresh" then begin
    fetch_actors ();
    (match !selected_actor with Some _ -> refresh_source () | None -> ());
    mark_status "refreshed"
  end
  else if l = "clear" then begin
    Queue.clear output_lines;
    output_scroll := 0
  end
  else if l = "?" || l = "help-tui" then do_help_tui ()
  else if String.length l > 7 && String.sub l 0 7 = "select " then begin
    let name = String.trim (String.sub l 7 (String.length l - 7)) in
    if name = "" then add_output_text "[tui] usage: select <name>"
    else begin
      selected_actor := Some name;
      add_output_text ("[tui] selected: " ^ name);
      refresh_source ()
    end
  end
  else begin
    (* Send to REPL *)
    add_output_text ("AIPL> " ^ l);
    let out = send_repl_command l in
    add_output_text out;
    (* opportunistic refresh *)
    if (let ll = String.lowercase_ascii l in
        let is_pfx p = String.length ll >= String.length p
                       && String.sub ll 0 (String.length p) = p in
        is_pfx "compile" || is_pfx "load " || is_pfx "script "
        || is_pfx "send " || is_pfx "ssend " || is_pfx "reset")
    then fetch_actors ()
  end;
  dirty := true

(* ================================================================== *)
(*                          Input handling                             *)
(* ================================================================== *)

(* Read a key sequence. Returns a symbolic key name plus a string payload. *)
type key =
  | K_char of char
  | K_enter
  | K_backspace
  | K_ctrl of char
  | K_up | K_down | K_left | K_right
  | K_home | K_end
  | K_pgup | K_pgdn
  | K_fn of int
  | K_esc
  | K_none

let stdin_buf = Bytes.create 32

let read_key () : key =
  let n =
    try read stdin stdin_buf 0 (Bytes.length stdin_buf) with Unix_error _ -> 0
  in
  if n = 0 then K_none
  else begin
    let b i = Char.code (Bytes.get stdin_buf i) in
    let c0 = b 0 in
    if c0 = 0x0A || c0 = 0x0D then K_enter
    else if c0 = 0x7F || c0 = 0x08 then K_backspace
    else if c0 = 0x04 then K_ctrl 'd'
    else if c0 = 0x03 then K_ctrl 'c'
    else if c0 = 0x0C then K_ctrl 'l'
    else if c0 = 0x1B then begin
      if n = 1 then K_esc
      else if n >= 3 && b 1 = Char.code '[' then begin
        match Char.chr (b 2) with
        | 'A' -> K_up
        | 'B' -> K_down
        | 'C' -> K_right
        | 'D' -> K_left
        | 'H' -> K_home
        | 'F' -> K_end
        | '5' -> K_pgup
        | '6' -> K_pgdn
        | _ -> K_none
      end
      else if n >= 3 && b 1 = Char.code 'O' then begin
        (* xterm F-keys: ESC O P .. ESC O S *)
        match Char.chr (b 2) with
        | 'P' -> K_fn 1
        | 'Q' -> K_fn 2
        | 'R' -> K_fn 3
        | 'S' -> K_fn 4
        | _ -> K_none
      end
      else K_esc
    end
    else if c0 >= 32 && c0 < 127 then K_char (Char.chr c0)
    else K_none
  end

let handle_key k =
  match k with
  | K_none -> ()
  | K_esc -> ()
  | K_ctrl 'd' -> quit_requested := true
  | K_ctrl 'l' -> dirty := true
  | K_ctrl 'c' -> set_input ""; dirty := true
  | K_fn 1 | K_char '?' when Buffer.length input_buf = 0 ->
      do_help_tui (); dirty := true
  | K_fn 2 ->
      dispatch_command "compile"; dirty := true
  | K_fn 5 ->
      fetch_actors ();
      (match !selected_actor with Some _ -> refresh_source () | None -> ());
      dirty := true
  | K_fn 10 ->
      quit_requested := true
  | K_enter ->
      let line = input_string () in
      push_history line;
      history_pos := -1;
      set_input "";
      dispatch_command line
  | K_backspace ->
      let s = input_string () in
      let n = String.length s in
      if !input_cursor > 0 && n > 0 then begin
        let s' = String.sub s 0 (!input_cursor - 1)
                 ^ String.sub s !input_cursor (n - !input_cursor) in
        set_input s';
        (* cursor now at (old - 1), but set_input reset it to end; fix *)
        input_cursor := String.length s' - (n - !input_cursor);
        dirty := true
      end
  | K_left  ->
      if !input_cursor > 0 then (decr input_cursor; dirty := true)
  | K_right ->
      if !input_cursor < Buffer.length input_buf then
        (incr input_cursor; dirty := true)
  | K_home  -> input_cursor := 0; dirty := true
  | K_end   -> input_cursor := Buffer.length input_buf; dirty := true
  | K_up ->
      if !history_count > 0 then begin
        let new_pos =
          if !history_pos < 0 then !history_count - 1
          else max 0 (!history_pos - 1)
        in
        history_pos := new_pos;
        set_input history.(new_pos);
        dirty := true
      end
  | K_down ->
      if !history_count > 0 then begin
        if !history_pos < 0 then ()
        else if !history_pos >= !history_count - 1 then begin
          history_pos := -1;
          set_input "";
          dirty := true
        end else begin
          incr history_pos;
          set_input history.(!history_pos);
          dirty := true
        end
      end
  | K_pgup ->
      output_scroll := !output_scroll + 5;
      dirty := true
  | K_pgdn ->
      output_scroll := max 0 (!output_scroll - 5);
      dirty := true
  | K_char c ->
      let s = input_string () in
      let cur = !input_cursor in
      let s' = String.sub s 0 cur ^ String.make 1 c
               ^ String.sub s cur (String.length s - cur) in
      set_input s';
      input_cursor := cur + 1;
      dirty := true
  | _ -> ()

(* ================================================================== *)
(*                            Main loop                                *)
(* ================================================================== *)

let last_fetch = ref 0.0
let fetch_interval = 2.0

let () =
  (* args: [-p port] [-h host] *)
  let args = Array.to_list Sys.argv in
  let rec parse = function
    | [] -> ()
    | "-p" :: p :: rest -> port := int_of_string p; parse rest
    | "-h" :: h :: rest -> host := h; parse rest
    | _ :: rest -> parse rest
  in
  parse (match args with _ :: t -> t | [] -> []);

  (* Wait briefly for server, up to 10 seconds. *)
  let ok = ref false in
  for _ = 1 to 20 do
    if not !ok then begin
      if ping_server () then ok := true
      else Unix.sleepf 0.5
    end
  done;
  if not !ok then begin
    Printf.printf "[tui] cannot connect to http://%s:%d — is repl_thread.exe running?\n"
      !host !port;
    exit 1
  end;

  (* Graceful exit on signals *)
  let restore_and_exit _ =
    leave_raw ();
    exit 0
  in
  Sys.set_signal Sys.sigint  (Sys.Signal_handle restore_and_exit);
  Sys.set_signal Sys.sigterm (Sys.Signal_handle restore_and_exit);

  refresh_term_size ();
  enter_raw ();

  add_output_text "[tui] connected. Type 'help-tui' or '?' for key bindings.";
  fetch_actors ();

  try
    while not !quit_requested do
      let now = Unix.gettimeofday () in
      if now -. !last_fetch >= fetch_interval then begin
        last_fetch := now;
        fetch_actors ()
      end;
      if !dirty then (draw_all (); dirty := false);
      let k = read_key () in
      (match k with K_none -> () | _ -> handle_key k)
    done;
    leave_raw ();
    Printf.printf "[tui] bye.\n%!"
  with exn ->
    leave_raw ();
    Printf.printf "[tui] unhandled error: %s\n%!" (Printexc.to_string exn);
    exit 1
