(* gui_ide.ml — Native SDL-based integrated environment for AIPL.

   Runs as a standalone executable with an SDL window. Processes commands
   entirely in-process (no HTTP): links directly to abcllib and drives
   Eval_thread / Typecheck / Parser from within the same binary.

   Layout (single window, four panes):
     ┌─ Header (title + hints) ──────────────────────────────────┐
     │ ┌ Output ─────────────────┐ ┌ Actors ───────────────────┐ │
     │ │                         │ │                           │ │
     │ ├─ Source ────────────────┤ │                           │ │
     │ │                         │ │                           │ │
     │ └─────────────────────────┘ └───────────────────────────┘ │
     │  AIPL> <command input>                                  │
     └────────────────────────────────────────────────────────────┘

   Keys:
     Enter          submit command
     Backspace      erase last char
     ←/→            move cursor
     ↑/↓            command history
     Tab            switch selected actor (cycle)
     PageUp/Down    scroll output pane
     F2             compile
     F5             refresh
     F10 / Esc Esc  quit
*)

open Tsdl
open Ast

(* ================================================================== *)
(*                 stdout/stderr capture into Output pane              *)
(* ================================================================== *)

let capture_buf_mu = Mutex.create ()
let capture_lines : string Queue.t = Queue.create ()
let max_output_lines = 800
let capture_partial = Buffer.create 256

(* Forward declaration: the main loop flips this to trigger a redraw.
   Capture callers bump it whenever new output arrives, so the Output
   pane refreshes immediately instead of waiting for the periodic tick. *)
let dirty_flag : bool ref = ref true

let push_capture_line line =
  Mutex.lock capture_buf_mu;
  Queue.add line capture_lines;
  while Queue.length capture_lines > max_output_lines do
    ignore (Queue.pop capture_lines)
  done;
  Mutex.unlock capture_buf_mu;
  dirty_flag := true

let push_captured_text (s:string) =
  Mutex.lock capture_buf_mu;
  String.iter (fun c ->
    if c = '\n' then begin
      Queue.add (Buffer.contents capture_partial) capture_lines;
      Buffer.clear capture_partial;
      while Queue.length capture_lines > max_output_lines do
        ignore (Queue.pop capture_lines)
      done
    end else if c <> '\r' then
      Buffer.add_char capture_partial c
  ) s;
  Mutex.unlock capture_buf_mu;
  dirty_flag := true

let snapshot_capture () =
  Mutex.lock capture_buf_mu;
  let lines =
    Queue.fold (fun acc l -> l :: acc) [] capture_lines |> List.rev
  in
  let tail = Buffer.contents capture_partial in
  Mutex.unlock capture_buf_mu;
  if tail = "" then lines else lines @ [tail]

let clear_output () =
  Mutex.lock capture_buf_mu;
  Queue.clear capture_lines;
  Buffer.clear capture_partial;
  Mutex.unlock capture_buf_mu

(* Redirect stdout/stderr through a pipe; reader thread pushes into the
   output buffer so everything Printf.printf'd from Eval_thread etc. shows
   up in the GUI Output pane. *)
let start_stdio_capture () =
  let (r, w) = Unix.pipe () in
  (* dup the pipe-write over fd 1 and fd 2 *)
  Unix.dup2 w Unix.stdout;
  Unix.dup2 w Unix.stderr;
  Unix.close w;
  let _reader =
    Thread.create (fun () ->
      let buf = Bytes.create 4096 in
      let running = ref true in
      while !running do
        try
          let n = Unix.read r buf 0 (Bytes.length buf) in
          if n <= 0 then running := false
          else push_captured_text (Bytes.sub_string buf 0 n)
        with _ -> running := false
      done
    ) ()
  in
  ()

(* A logging helper that writes straight to the Output pane (bypassing
   captured stdout) so the GUI has a guaranteed path even if stdout is
   redirected. *)
let glog line = push_capture_line line

(* ================================================================== *)
(*                       Command processing (in-proc)                  *)
(* ================================================================== *)

let program_buffer : Ast.program ref = ref []
let pending_global_sends : (unit -> unit) list ref = ref []

(* Adapted from repl_thread.ml — parse input into an Ast.program. *)
let parse_program_safe (src:string) : (Ast.program, string) result =
  let lb = Lexing.from_string src in
  try
    lb.Lexing.lex_curr_pos <- 0;
    Ok (Parser.program Lexer.token lb)
  with
  | Failure msg -> Error ("Failure: " ^ msg)
  | Parsing.Parse_error ->
      let pos = Lexing.lexeme_start_p lb in
      let line = pos.Lexing.pos_lnum in
      let col  = pos.Lexing.pos_cnum - pos.Lexing.pos_bol + 1 in
      Error (Printf.sprintf "Parse error at line %d, col %d" line col)
  | exn -> Error (Printexc.to_string exn)

let parse_file_safe (fname:string) : (Ast.program, string) result =
  try
    let ic = open_in fname in
    let len = in_channel_length ic in
    let s = really_input_string ic len in
    close_in ic;
    parse_program_safe s
  with Sys_error e -> Error ("Sys_error: " ^ e)

let trim = String.trim

(* Strip a single pair of surrounding double quotes, if present.
   Lets `load "abclc/Foo.abcl"` and `load abclc/Foo.abcl` both work. *)
let unquote (s:string) : string =
  let n = String.length s in
  if n >= 2 && s.[0] = '"' && s.[n-1] = '"' then String.sub s 1 (n - 2)
  else s

let starts_with s p =
  let ls = String.length s and lp = String.length p in
  ls >= lp && String.sub s 0 lp = p

let string_of_send_target = function
  | LocalTarget t -> t
  | RemoteTarget (hp, a) -> "remote(" ^ hp ^ ", " ^ a ^ ")"

let parse_arg_token (t:string) : Ast.expr =
  let t = trim t in
  let n = String.length t in
  if n >= 2 && t.[0] = '"' && t.[n-1] = '"' then
    Ast.mk_expr (Ast.String (String.sub t 1 (n - 2)))
  else
    match int_of_string_opt t with
    | Some i -> Ast.mk_int i
    | None ->
        (match float_of_string_opt t with
         | Some f -> Ast.mk_float f
         | None -> Ast.mk_expr (Ast.Var t))

let split_args (s:string) : string list =
  let rec loop i start acc =
    if i >= String.length s then
      let last = String.sub s start (i - start) in
      List.rev (last :: acc)
    else
      match s.[i] with
      | ',' ->
          loop (i+1) (i+1) (String.sub s start (i - start) :: acc)
      | _ -> loop (i+1) start acc
  in
  let s = trim s in
  if s = "" then [] else List.map trim (loop 0 0 [])

let parse_args_list s : Ast.expr list =
  split_args s |> List.map parse_arg_token

(* Most-recently-loaded source file, displayed in a side pane with line
   numbers. Updated whenever `load <file>` succeeds (including script-driven
   loads). *)
let loaded_src_path : string option ref = ref None
let loaded_src_text : string ref = ref ""
let loaded_src_scroll : int ref = ref 0

let read_file_safe fname =
  try
    let ic = open_in fname in
    let n = in_channel_length ic in
    let s = really_input_string ic n in
    close_in ic; Some s
  with _ -> None

let load_file (fname:string) : Ast.program option =
  match parse_file_safe fname with
  | Error msg ->
      glog (Printf.sprintf "[Error] could not load %s: %s" fname msg);
      None
  | Ok decls ->
      if Typecheck.run decls then begin
        glog (Printf.sprintf "[Loaded] %s" fname);
        (match read_file_safe fname with
         | Some s ->
             loaded_src_path := Some fname;
             loaded_src_text := s;
             loaded_src_scroll := 0
         | None -> ());
        Some decls
      end else begin
        glog (Printf.sprintf "[Abort] Type error while loading %s" fname);
        None
      end

let run_compile () =
  List.iter (function
    | Class obj ->
        glog (Printf.sprintf "[Defined class %s]" obj.cname);
        Eval_thread.register_class obj;
        let ms_arity : (string * int) list =
          obj.methods |> List.map
            (fun (md:Ast.method_decl) -> (md.mname, List.length md.params))
        in
        Types.register_class_auto obj.cname ms_arity
    | _ -> ()
  ) !program_buffer;
  List.iter (function
    | Global s -> begin
        match s.sdesc with
        | VarDecl (name, rhs) -> begin
            match rhs.desc with
            | New (cls, args) ->
                let cobj = Eval_thread.find_class_exn cls in
                Eval_thread.register_instance_source name cobj;
                let obj = { cobj with cname = cls } in
                let actor_inst = Eval_thread.create_actor name cls in
                List.iter (fun (st:Ast.stmt) ->
                  match st.sdesc with
                  | VarDecl (k, init) ->
                      let v = Eval_thread.eval_expr actor_inst init in
                      Hashtbl.replace actor_inst.env k v
                  | _ -> ()
                ) obj.fields;
                List.iter (fun (m:method_decl) ->
                  Hashtbl.replace actor_inst.methods m.mname m
                ) obj.methods;
                Hashtbl.add Eval_thread.actor_table name actor_inst;
                ignore (Thread.create
                          (fun () -> Eval_thread.actor_loop actor_inst) ());
                let init_opt =
                  List.find_opt (fun (m:Ast.method_decl) -> m.mname = "init")
                    obj.methods
                in
                (match init_opt with
                 | None ->
                     glog (Printf.sprintf "[Actor] %s: no init; skipped" name)
                 | Some m ->
                     let need = List.length m.params and got = List.length args in
                     if need <> got then
                       glog (Printf.sprintf
                               "[Actor] %s.init arity mismatch: expected %d but %d"
                               name need got)
                     else
                       Eval_thread.send_message ~from:"<new>" name
                         (mk_stmt (CallStmt ("init", args))))
            | _ -> ()
          end
        | Send (tgt, mname, args) ->
            pending_global_sends :=
              (fun () ->
                Eval_thread.send_message ~from:"<top>"
                  (string_of_send_target tgt)
                  (mk_stmt (CallStmt (mname, args))))
              :: !pending_global_sends
        | UnsafeSend (tgt, mname, args) ->
            pending_global_sends :=
              (fun () ->
                Eval_thread.send_message ~from:"<top>"
                  (string_of_send_target tgt)
                  (mk_stmt (CallStmt (mname, args))))
              :: !pending_global_sends
        | CallStmt (fname, args) ->
            let dummy = Eval_thread.create_actor "<top>" "<top>" in
            (try
               let vs = List.map (Eval_thread.eval_expr dummy) args in
               ignore (Eval_thread.call_prim fname vs)
             with exn ->
               glog (Printf.sprintf "[Top-level CallStmt error] %s"
                       (Printexc.to_string exn)))
        | _ -> ()
      end
    | Class _ -> ()
  ) !program_buffer;
  List.iter (fun thunk -> thunk ()) (List.rev !pending_global_sends);
  pending_global_sends := [];
  glog "[Compiled]"

let cmd_help () =
  glog "Commands:";
  glog "  help                   - show this help";
  glog "  load <file>            - load .abcl source";
  glog "  script <file>          - run .bat REPL-commands file";
  glog "  compile                - instantiate actors";
  glog "  list / actors          - refresh actor list";
  glog "  send <obj>.<m>(args)   - send async message";
  glog "  kill <name>            - stop a running actor";
  glog "  kill / kill all        - stop all running actors";
  glog "  pprint <name>          - show source in source pane";
  glog "  ast <name>             - show AST in source pane";
  glog "  select <name>          - select actor for source pane";
  glog "  clear                  - clear output";
  glog "  quit / exit            - leave GUI"

let selected_actor : string option ref = ref None
let source_text    : string ref = ref "(アクタを選択してください)"

let do_pprint name =
  match Eval_thread.get_instance_source name with
  | Some cdecl -> source_text := Ast.pprint_class cdecl; selected_actor := Some name
  | None ->
      (match Hashtbl.find_opt Eval_thread.class_env name with
       | Some cdecl ->
           source_text := Ast.pprint_class cdecl;
           selected_actor := Some name
       | None ->
           source_text := "[Error] no source for '" ^ name ^ "'")

let do_ast name =
  let buf = Buffer.create 256 in
  let old = Stdlib.stdout in
  (* We can't easily capture dump_program output without redirecting. Since
     stdout is already piped to the Output pane, just use it and rely on a
     separate path through source_text. Simpler: don't show AST in source
     pane; instead dump it to the Output pane. *)
  ignore old; ignore buf;
  match Eval_thread.get_instance_source name with
  | Some cdecl ->
      Ast.dump_decl ~prefix:"" ~is_last:true (Class cdecl);
      selected_actor := Some name
  | None ->
      (match (try Some (Eval_thread.find_class_exn name) with _ -> None) with
       | Some cdecl ->
           Ast.dump_decl ~prefix:"" ~is_last:true (Class cdecl);
           selected_actor := Some name
       | None ->
           glog (Printf.sprintf "[Error] no AST for '%s'" name))

(* Main command dispatcher. Returns false if the caller should quit. *)
let rec process_command (line:string) : bool =
  let line = String.trim line in
  if line = "" then true
  else if line = "quit" || line = "exit" then false
  else if line = "help" then (cmd_help (); true)
  else if line = "clear" then (clear_output (); true)
  else if line = "compile" then (run_compile (); true)
  else if line = "list" || line = "actors" then begin
    glog "[actors]";
    Eval_thread.iter_actor_table (fun aname a ->
      let cls = Eval_thread.actor_class_name aname a in
      let mbox = Eval_thread.mailbox_len a in
      let methods = Eval_thread.method_names a in
      glog (Printf.sprintf "- %s : %s (mbox=%d, methods: %s)"
              aname cls mbox
              (if methods = [] then "(none)" else String.concat ", " methods))
    );
    true
  end
  else if starts_with line "load " then begin
    let fname = unquote (trim (String.sub line 5 (String.length line - 5))) in
    (match load_file fname with
     | Some decls -> program_buffer := !program_buffer @ decls
     | None -> ());
    true
  end
  else if starts_with line "script " then begin
    let fname = unquote (trim (String.sub line 7 (String.length line - 7))) in
    (* Show the script's own contents in the Source pane immediately;
       commands inside (e.g. `load X.abcl`) may then overwrite it. *)
    (match read_file_safe fname with
     | Some s ->
         loaded_src_path := Some fname;
         loaded_src_text := s;
         loaded_src_scroll := 0
     | None -> ());
    (try
       let ic = open_in fname in
       let saved_cwd = try Some (Sys.getcwd ()) with _ -> None in
       let script_dir = Filename.dirname fname in
       let chdir_ok =
         if script_dir = "" || script_dir = "." then false
         else try Sys.chdir script_dir; true with _ -> false
       in
       if chdir_ok then glog (Printf.sprintf "[script] cwd -> %s" script_dir);
       let restore () =
         if chdir_ok then
           match saved_cwd with
           | Some d -> (try Sys.chdir d with _ -> ())
           | None -> ()
       in
       (try
          while true do
            let cmd = input_line ic in
            glog ("[script] " ^ cmd);
            try ignore (process_command cmd)
            with exn ->
              glog (Printf.sprintf "[Error in script line] %s"
                      (Printexc.to_string exn))
          done
        with End_of_file ->
          close_in ic;
          restore ();
          glog "[Script execution completed]")
     with Sys_error msg ->
       glog ("[Error] Could not open script file: " ^ msg));
    true
  end
  else if line = "kill" || line = "kill all" then begin
    let names = ref [] in
    Eval_thread.iter_actor_table (fun a _ -> names := a :: !names);
    List.iter (fun name ->
      match Hashtbl.find_opt Eval_thread.actor_table name with
      | Some a ->
          Mutex.lock a.Eval_thread.mutex;
          Queue.clear a.Eval_thread.queue;
          Mutex.unlock a.Eval_thread.mutex;
          Hashtbl.remove Eval_thread.actor_table name
      | None -> ()
    ) !names;
    if !selected_actor <> None then selected_actor := None;
    glog (Printf.sprintf "[Kill] stopped %d actor(s)" (List.length !names));
    true
  end
  else if starts_with line "kill " then begin
    let name = trim (String.sub line 5 (String.length line - 5)) in
    (match Hashtbl.find_opt Eval_thread.actor_table name with
     | Some a ->
         Mutex.lock a.Eval_thread.mutex;
         Queue.clear a.Eval_thread.queue;
         Mutex.unlock a.Eval_thread.mutex;
         Hashtbl.remove Eval_thread.actor_table name;
         if !selected_actor = Some name then selected_actor := None;
         glog (Printf.sprintf "[Kill] %s stopped" name)
     | None -> glog (Printf.sprintf "[Kill] no such actor: %s" name));
    true
  end
  else if starts_with line "pprint " then begin
    let name = trim (String.sub line 7 (String.length line - 7)) in
    do_pprint name;
    true
  end
  else if starts_with line "ast " then begin
    let name = trim (String.sub line 4 (String.length line - 4)) in
    do_ast name;
    true
  end
  else if starts_with line "select " then begin
    let name = trim (String.sub line 7 (String.length line - 7)) in
    if name = "" then glog "[gui] usage: select <name>"
    else do_pprint name;
    true
  end
  else if starts_with line "send " then begin
    let payload = trim (String.sub line 5 (String.length line - 5)) in
    (try
       let lparen = String.index payload '(' in
       let rparen = String.rindex payload ')' in
       if rparen <= lparen then failwith "syntax: send obj.m(args)";
       let head = trim (String.sub payload 0 lparen) in
       let ainside = String.sub payload (lparen+1) (rparen - lparen - 1) in
       match String.split_on_char '.' head with
       | [obj; meth] ->
           let args = parse_args_list ainside in
           Eval_thread.send_message ~from:"gui" obj
             (mk_stmt (CallStmt (meth, args)))
       | _ -> glog "[Error] send target must be <obj>.<method>(args)"
     with
     | Not_found -> glog "[Error] send: missing '(' or ')'"
     | exn -> glog ("[Error] send: " ^ Printexc.to_string exn));
    true
  end
  else begin
    (* Try to parse as ABCL source. *)
    match parse_program_safe line with
    | Error msg ->
        glog ("[Parse error] " ^ msg);
        true
    | Ok decls ->
        if Typecheck.run decls then begin
          program_buffer := !program_buffer @ decls;
          glog "[Loaded] <gui>";
          true
        end else begin
          glog "[Abort] Type error while parsing input";
          true
        end
  end

(* ================================================================== *)
(*                          SDL / UI plumbing                          *)
(* ================================================================== *)

let sdl_err = function Ok x -> x | Error (`Msg m) -> failwith ("SDL: " ^ m)

let font_scale = 1   (* 8x8 native — one step smaller than the previous 2x *)
let cell_w = Gui_font.glyph_width * font_scale
let cell_h = Gui_font.glyph_height * font_scale
let line_h = cell_h + 4   (* vertical gap between lines *)

(* Default window size *)
let win_w_init = 1400
let win_h_init = 900

let win_w = ref win_w_init
let win_h = ref win_h_init

(* Use the logical window size for everything so mouse coordinates (which
   SDL reports in logical coords) line up with our draw coordinates. The
   renderer scales automatically to the framebuffer on HiDPI displays. *)
let refresh_window_size ?(renderer=None) window =
  let _ = renderer in
  let (w, h) = Sdl.get_window_size window in
  win_w := w;
  win_h := h

type rgb = { r:int; g:int; b:int }
let c_bg          = { r = 30; g = 30; b = 30 }
let c_pane_bg     = { r = 37; g = 37; b = 38 }
let c_dark_bg     = { r = 18; g = 18; b = 18 }
let c_header_bg   = { r = 45; g = 45; b = 48 }
let c_border      = { r = 60; g = 60; b = 60 }
let c_fg          = { r = 220; g = 220; b = 220 }
let c_muted       = { r = 158; g = 158; b = 158 }
let c_accent      = { r = 79; g = 195; b = 247 }
let c_accent2     = { r = 255; g = 202; b = 40 }
let c_err         = { r = 239; g = 83; b = 80 }
let c_ok          = { r = 139; g = 195; b = 74 }
let c_selbg       = { r = 9; g = 71; b = 113 }

let set_color r c =
  sdl_err (Sdl.set_render_draw_color r c.r c.g c.b 255)

let fill_rect r ~x ~y ~w ~h c =
  set_color r c;
  let rect = Sdl.Rect.create ~x ~y ~w ~h in
  sdl_err (Sdl.render_fill_rect r (Some rect))

let stroke_rect r ~x ~y ~w ~h c =
  set_color r c;
  let rect = Sdl.Rect.create ~x ~y ~w ~h in
  sdl_err (Sdl.render_draw_rect r (Some rect))

let draw_char r px py c color =
  set_color r color;
  let rows = Gui_font.glyph c in
  for y = 0 to 7 do
    let row = rows.(y) in
    for x = 0 to 7 do
      if (row lsr (7 - x)) land 1 = 1 then begin
        let rect = Sdl.Rect.create
          ~x:(px + x * font_scale)
          ~y:(py + y * font_scale)
          ~w:font_scale ~h:font_scale
        in
        sdl_err (Sdl.render_fill_rect r (Some rect))
      end
    done
  done

let draw_string r px py s color =
  let x = ref px in
  String.iter (fun c ->
    draw_char r !x py c color;
    x := !x + cell_w
  ) s

let draw_string_clipped r px py max_w s color =
  let maxchars = max 0 (max_w / cell_w) in
  let s =
    if String.length s <= maxchars then s
    else if maxchars <= 1 then String.sub s 0 maxchars
    else String.sub s 0 (maxchars - 1) ^ "~"
  in
  draw_string r px py s color

(* ================================================================== *)
(*                             UI state                                *)
(* ================================================================== *)

let input_buf = Buffer.create 256
let input_cursor = ref 0

let set_input s =
  Buffer.clear input_buf;
  Buffer.add_string input_buf s;
  input_cursor := String.length s

let history : string array = Array.make 100 ""
let history_count = ref 0
let history_pos   = ref (-1)

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

let output_scroll = ref 0         (* >0 = lines from tail *)
let status_msg = ref ""
(* Share with dirty_flag so capture callers can trigger redraws. *)
let dirty = dirty_flag

let quit_requested = ref false

let current_input () = Buffer.contents input_buf

(* ================================================================== *)
(*                              Panes                                  *)
(* ================================================================== *)

type pane = {
  mutable px: int;
  mutable py: int;
  mutable pw: int;
  mutable ph: int;
}

let p_output = { px=0; py=0; pw=0; ph=0 }
let p_source = { px=0; py=0; pw=0; ph=0 }
let p_actors = { px=0; py=0; pw=0; ph=0 }
let p_input  = { px=0; py=0; pw=0; ph=0 }
(* All vertical chrome sizes derive from cell_h so changing font_scale
   keeps the layout in proportion. *)
let header_h   = cell_h + 16
let toolbar_h  = cell_h + 24
let footer_h   = cell_h + 12

(* Toolbar button spec *)
type button = {
  mutable bx: int;
  mutable by: int;
  mutable bw: int;
  mutable bh: int;
  blabel: string;
  baction: unit -> unit;
}

let make_btn label action =
  { bx=0; by=0; bw=0; bh=0; blabel=label; baction=action }

(* Defined later once we know how to drive the file browser / compile. *)
let buttons : button list ref = ref []

(* Command input pane is sized for 5 visible rows, per user request.
   Text wraps across rows; Enter still submits the full input. *)
let input_rows = 5

let relayout () =
  let w = !win_w and h = !win_h in
  let input_h = line_h * input_rows + 16 in
  let body_top = header_h + toolbar_h in
  let body_h = h - body_top - footer_h - input_h in
  let left_w = max 420 (w * 3 / 5) in
  let right_w = w - left_w in
  let out_h = max 200 (body_h * 3 / 5) in
  let src_h = body_h - out_h in
  p_output.px <- 0;      p_output.py <- body_top;
  p_output.pw <- left_w; p_output.ph <- out_h;
  p_source.px <- 0;      p_source.py <- body_top + out_h;
  p_source.pw <- left_w; p_source.ph <- src_h;
  p_actors.px <- left_w; p_actors.py <- body_top;
  p_actors.pw <- right_w; p_actors.ph <- body_h;
  p_input.px  <- 0;      p_input.py <- body_top + body_h;
  p_input.pw  <- w;      p_input.ph <- input_h;
  (* Layout toolbar buttons *)
  let bx = ref 10 in
  let by = header_h + 6 in
  let bh = toolbar_h - 12 in
  List.iter (fun b ->
    let w = String.length b.blabel * cell_w + 24 in
    b.bx <- !bx;
    b.by <- by;
    b.bw <- w;
    b.bh <- bh;
    bx := !bx + w + 8
  ) !buttons

let pane_title_h = cell_h + 12

let draw_pane_frame r p ~title ~title_color =
  fill_rect r ~x:p.px ~y:p.py ~w:p.pw ~h:p.ph c_pane_bg;
  stroke_rect r ~x:p.px ~y:p.py ~w:p.pw ~h:p.ph c_border;
  (* title bar strip *)
  fill_rect r ~x:(p.px+1) ~y:(p.py+1) ~w:(p.pw-2) ~h:(pane_title_h-2) c_header_bg;
  draw_string r (p.px + 10) (p.py + 6) title title_color

let pane_content_rect p =
  let content_top = p.py + pane_title_h in
  let content_bottom = p.py + p.ph - 4 in
  (p.px + 8, content_top + 4, p.pw - 16, content_bottom - content_top - 4)

let mouse_x = ref 0
let mouse_y = ref 0
let mouse_over_btn : button option ref = ref None

(* Hit regions rebuilt every redraw. (name, y_top, y_bottom). *)
let actor_hit_rows : (string * int * int) list ref = ref []
let mouse_over_actor : string option ref = ref None

let hit_button b mx my =
  mx >= b.bx && mx < b.bx + b.bw
  && my >= b.by && my < b.by + b.bh

let draw_header r =
  fill_rect r ~x:0 ~y:0 ~w:!win_w ~h:header_h c_header_bg;
  let title = "AIPL GUI IDE" in
  let title_y = (header_h - cell_h) / 2 in
  draw_string r 10 title_y title c_accent;
  (* Compact hint, shown only when there's space after the title. *)
  let hint = "F1:help  F10:quit" in
  let hint_w = String.length hint * cell_w in
  let title_w = String.length title * cell_w in
  if !win_w > title_w + hint_w + 60 then
    draw_string r (!win_w - hint_w - 10) title_y hint c_muted

let c_btn_bg      = { r = 55; g = 55; b = 58 }
let c_btn_bg_hov  = { r = 80; g = 80; b = 85 }
let c_btn_border  = { r = 90; g = 90; b = 95 }
let c_btn_fg      = { r = 230; g = 230; b = 230 }
let c_btn_file    = { r = 14; g = 99; b = 156 }
let c_btn_file_h  = { r = 18; g = 119; b = 187 }

let is_file_button b = (b.blabel = "File")

let draw_toolbar r =
  fill_rect r ~x:0 ~y:header_h ~w:!win_w ~h:toolbar_h c_bg;
  List.iter (fun b ->
    let hov = (Some b == !mouse_over_btn) in
    let bgc =
      if is_file_button b then
        (if hov then c_btn_file_h else c_btn_file)
      else
        (if hov then c_btn_bg_hov else c_btn_bg)
    in
    fill_rect r ~x:b.bx ~y:b.by ~w:b.bw ~h:b.bh bgc;
    stroke_rect r ~x:b.bx ~y:b.by ~w:b.bw ~h:b.bh c_btn_border;
    let tx = b.bx + (b.bw - String.length b.blabel * cell_w) / 2 in
    let ty = b.by + (b.bh - cell_h) / 2 in
    draw_string r tx ty b.blabel c_btn_fg
  ) !buttons

let draw_status r =
  let y = !win_h - footer_h in
  fill_rect r ~x:0 ~y ~w:!win_w ~h:footer_h c_header_bg;
  let ty = y + (footer_h - cell_h) / 2 in
  let msg =
    if !status_msg = "" then
      let n_actors = ref 0 in
      Eval_thread.iter_actor_table (fun _ _ -> incr n_actors);
      let sel = match !selected_actor with Some s -> s | None -> "-" in
      Printf.sprintf "actors=%d  sel=%s  hist=%d"
        !n_actors sel !history_count
    else !status_msg
  in
  draw_string_clipped r 10 ty (!win_w - 20) msg c_muted

let line_color_of line =
  if String.length line >= 9 && String.sub line 0 9 = "AIPL> " then c_accent
  else if String.length line > 0 && line.[0] = '[' then begin
    let low = String.lowercase_ascii line in
    if starts_with low "[error]" || starts_with low "[failed]" || starts_with low "[abort]"
      || starts_with low "[parse error]" || starts_with low "[type error]"
      then c_err
    else if starts_with low "[reply]" || starts_with low "[compiled]" || starts_with low "[loaded]"
      then c_ok
    else c_muted
  end
  else c_fg

let draw_output r =
  draw_pane_frame r p_output ~title:"Output" ~title_color:c_accent;
  let (cx, cy, cw, ch) = pane_content_rect p_output in
  fill_rect r ~x:cx ~y:cy ~w:cw ~h:ch c_dark_bg;
  let all = snapshot_capture () in
  let n = List.length all in
  let visible = ch / line_h in
  let scroll = min !output_scroll (max 0 (n - visible)) in
  let start = max 0 (n - visible - scroll) in
  let stop  = n - scroll in
  let y = ref (cy + 4) in
  List.iteri (fun i line ->
    if i >= start && i < stop && !y + line_h <= cy + ch then begin
      draw_string_clipped r (cx + 4) !y (cw - 8) line (line_color_of line);
      y := !y + line_h
    end
  ) all

let ellipsize s n =
  if String.length s <= n then s
  else if n <= 1 then String.sub s 0 n
  else String.sub s 0 (n - 1) ^ "~"

let draw_actors r =
  draw_pane_frame r p_actors ~title:"Current Actors" ~title_color:c_accent;
  let (cx, cy, cw, ch) = pane_content_rect p_actors in
  fill_rect r ~x:cx ~y:cy ~w:cw ~h:ch c_dark_bg;
  actor_hit_rows := [];
  (* collect actors *)
  let actors = ref [] in
  Eval_thread.iter_actor_table (fun aname a ->
    let cls = Eval_thread.actor_class_name aname a in
    let mbox = Eval_thread.mailbox_len a in
    let methods = Eval_thread.method_names a in
    actors := (aname, cls, mbox, methods) :: !actors
  );
  let actors = List.sort (fun (a,_,_,_) (b,_,_,_) -> compare a b) !actors in
  if actors = [] then begin
    draw_string_clipped r (cx + 8) (cy + 8) (cw - 16)
      "(まだアクタが登録されていません -- ツールバーのデモを押して下さい)" c_muted
  end else begin
    let maxchars = (cw - 16) / cell_w in
    let y = ref (cy + 4) in
    List.iter (fun (aname, cls, mbox, methods) ->
      if !y + line_h * 2 > cy + ch then () else begin
        let row_top = !y in
        let row_bot = !y + line_h * 2 in
        let sel = (Some aname = !selected_actor) in
        let hov = (Some aname = !mouse_over_actor) in
        let bg = if sel then Some c_selbg
                 else if hov then Some c_btn_bg
                 else None in
        (match bg with
         | Some b -> fill_rect r ~x:cx ~y:row_top ~w:cw ~h:(line_h*2) b
         | None -> ());
        let prefix = if sel then "> " else "  " in
        draw_string r (cx + 8) (!y + 2)
          (ellipsize (prefix ^ aname ^ " : " ^ cls) maxchars)
          c_accent2;
        y := !y + line_h;
        let meta = Printf.sprintf "    mbox=%d  %s" mbox
          (if methods = [] then "(no methods)"
           else "methods: " ^ String.concat ", " methods)
        in
        draw_string_clipped r (cx + 8) (!y + 2) (cw - 16) meta c_muted;
        y := !y + line_h + 4;
        actor_hit_rows :=
          (aname, row_top, row_bot) :: !actor_hit_rows
      end
    ) actors
  end

let draw_source r =
  let title = match !loaded_src_path with
    | Some p -> "Source: " ^ p
    | None -> "Source"
  in
  draw_pane_frame r p_source ~title ~title_color:c_accent;
  let (cx, cy, cw, ch) = pane_content_rect p_source in
  fill_rect r ~x:cx ~y:cy ~w:cw ~h:ch c_dark_bg;
  if !loaded_src_text = "" then
    draw_string_clipped r (cx + 8) (cy + 8) (cw - 16)
      "(load \"<file>.abcl\" / script \"<file>.bat\" でソースを表示)" c_muted
  else begin
    let lines = String.split_on_char '\n' !loaded_src_text in
    let total = List.length lines in
    let visible = max 1 (ch / line_h) in
    let max_scroll = max 0 (total - visible) in
    let scroll = min !loaded_src_scroll max_scroll in
    let gutter_digits = String.length (string_of_int (max 1 total)) in
    let gutter_w = (gutter_digits + 1) * cell_w in
    let y = ref (cy + 4) in
    List.iteri (fun i line ->
      let row = i - scroll in
      if row >= 0 && row < visible && !y + line_h <= cy + ch then begin
        let lineno = Printf.sprintf "%*d" gutter_digits (i + 1) in
        draw_string r (cx + 4) !y lineno c_muted;
        draw_string_clipped r (cx + 4 + gutter_w) !y
          (cw - 8 - gutter_w) line c_fg;
        y := !y + line_h
      end
    ) lines
  end

let draw_input r =
  fill_rect r ~x:p_input.px ~y:p_input.py ~w:p_input.pw ~h:p_input.ph c_header_bg;
  stroke_rect r ~x:p_input.px ~y:p_input.py ~w:p_input.pw ~h:p_input.ph c_border;
  let top_y = p_input.py + 8 in
  draw_string r 10 top_y "AIPL>" c_accent;
  let prompt_w = 10 * cell_w in
  let ix = prompt_w + 16 in
  let avail_w = p_input.pw - ix - 20 in
  let maxchars = max 1 (avail_w / cell_w) in
  let visible_rows = max 1 ((p_input.ph - 12) / line_h) in
  let s = current_input () in
  let n = String.length s in
  let cur = !input_cursor in
  let cur_row_full = cur / maxchars in
  let top_row = max 0 (cur_row_full - (visible_rows - 1)) in
  for row = 0 to visible_rows - 1 do
    let global_row = top_row + row in
    let start = global_row * maxchars in
    if start < n then begin
      let len = min maxchars (n - start) in
      let y = top_y + row * line_h in
      draw_string r ix y (String.sub s start len) c_fg
    end
  done;
  let cur_col = cur mod maxchars in
  let cur_y_row = cur_row_full - top_row in
  let cur_x = ix + cur_col * cell_w in
  let cur_y = top_y + cur_y_row * line_h in
  fill_rect r ~x:cur_x ~y:(cur_y - 2) ~w:(max 2 (cell_w / 6)) ~h:(cell_h + 4)
    c_accent

(* ================================================================== *)
(*                        File browser modal                           *)
(* ================================================================== *)

type fb_entry =
  | FBParent
  | FBDir of string   (* dir name only *)
  | FBFile of string  (* file name only *)

type fb_state = {
  mutable visible : bool;
  mutable dir     : string;    (* absolute path *)
  mutable entries : fb_entry list;
  mutable scroll  : int;       (* top index *)
  mutable hover   : int;       (* hovered index or -1 *)
  mutable ext     : string;    (* extension filter: "bat" / "abcl" / "" *)
  mutable error   : string;
}

let fb = {
  visible = false;
  dir     = (try Sys.getcwd () with _ -> ".");
  entries = [];
  scroll  = 0;
  hover   = -1;
  ext     = "";   (* "" = both .bat and .abcl, "bat" / "abcl" = single ext *)
  error   = "";
}

let fb_close_btn = { bx=0; by=0; bw=0; bh=0; blabel="Close"; baction=(fun () -> fb.visible <- false) }
let fb_bat_btn   = { bx=0; by=0; bw=0; bh=0; blabel=".bat"; baction=(fun () -> ()) }
let fb_abcl_btn  = { bx=0; by=0; bw=0; bh=0; blabel=".abcl"; baction=(fun () -> ()) }
let fb_all_btn   = { bx=0; by=0; bw=0; bh=0; blabel="Both"; baction=(fun () -> ()) }

(* Show only .bat and .abcl. fb.ext narrows to a single extension. *)
let fb_has_ext name =
  let low = String.lowercase_ascii name in
  let ends_with suf =
    let nl = String.length low and sl = String.length suf in
    nl > sl && String.sub low (nl - sl) sl = suf
  in
  match fb.ext with
  | "bat"  -> ends_with ".bat"
  | "abcl" -> ends_with ".abcl"
  | _      -> ends_with ".bat" || ends_with ".abcl"

let fb_load () =
  fb.error <- "";
  fb.entries <- [];
  fb.scroll <- 0;
  (try
     let arr = Sys.readdir fb.dir in
     Array.sort compare arr;
     let dirs = ref [] in
     let files = ref [] in
     Array.iter (fun name ->
       if name = "" || name.[0] = '.' then ()
       else
         let path =
           if fb.dir = "/" then "/" ^ name
           else Filename.concat fb.dir name
         in
         try
           if Sys.is_directory path then dirs := FBDir name :: !dirs
           else if fb_has_ext name then files := FBFile name :: !files
         with _ -> ()
     ) arr;
     let parent_ok =
       let p = Filename.dirname fb.dir in
       p <> fb.dir
     in
     let items =
       (if parent_ok then [FBParent] else [])
       @ List.rev !dirs
       @ List.rev !files
     in
     fb.entries <- items
   with Sys_error msg ->
     fb.error <- msg);
  dirty := true

let fb_open () =
  fb.visible <- true;
  fb_load ()

let fb_goto path =
  let p =
    if Filename.is_relative path then
      try Filename.concat (Sys.getcwd ()) path with _ -> path
    else path
  in
  fb.dir <- p;
  fb_load ()

let fb_open_entry e =
  match e with
  | FBParent ->
      fb_goto (Filename.dirname fb.dir)
  | FBDir name ->
      fb_goto (Filename.concat fb.dir name)
  | FBFile name ->
      let path = Filename.concat fb.dir name in
      let low = String.lowercase_ascii name in
      let quoted = "\"" ^ path ^ "\"" in
      let cmd =
        if Filename.check_suffix low ".bat" then Some ("script " ^ quoted)
        else if Filename.check_suffix low ".abcl" then Some ("load " ^ quoted)
        else None
      in
      (match cmd with
       | Some c ->
           glog ("[file] " ^ c);
           ignore (process_command c);
           fb.visible <- false;
           dirty := true
       | None ->
           glog ("[file] no runner for " ^ name))

(* Modal geometry (centered) *)
type modal_geom = {
  mx: int; my: int; mw: int; mh: int;
  topbar_h: int;
  list_y: int;
  list_h: int;
  row_h: int;
  max_rows: int;
}

let modal_geom () : modal_geom =
  let mw = min (!win_w - 100) 1100 in
  let mh = min (!win_h - 100) 760 in
  let mx = (!win_w - mw) / 2 in
  let my = (!win_h - mh) / 2 in
  let topbar_h = cell_h * 2 + 32 in
  let list_y = my + topbar_h in
  let bottom_bar_h = cell_h + 22 in
  let list_h = mh - topbar_h - bottom_bar_h in
  let row_h = cell_h + 10 in
  { mx; my; mw; mh; topbar_h; list_y; list_h; row_h;
    max_rows = list_h / row_h }

let layout_fb_buttons g =
  let close_w = 6 * cell_w + 24 in
  let close_h = cell_h + 14 in
  fb_close_btn.bx <- g.mx + g.mw - close_w - 10;
  fb_close_btn.by <- g.my + 10;
  fb_close_btn.bw <- close_w;
  fb_close_btn.bh <- close_h;
  (* Filter buttons at bottom *)
  let y = g.my + g.mh - cell_h - 16 in
  let h = cell_h + 12 in
  let place b x label =
    let w = String.length label * cell_w + 20 in
    b.bx <- x; b.by <- y; b.bw <- w; b.bh <- h; w
  in
  let w1 = place fb_bat_btn  (g.mx + 10) ".bat"  in
  let w2 = place fb_abcl_btn (g.mx + 10 + w1 + 6) ".abcl" in
  let _  = place fb_all_btn  (g.mx + 10 + w1 + 6 + w2 + 6) "Both" in
  ()

let draw_fb r =
  let g = modal_geom () in
  (* dim background *)
  set_color r { r=0; g=0; b=0 };
  let backdrop = Sdl.Rect.create ~x:0 ~y:0 ~w:!win_w ~h:!win_h in
  ignore (Sdl.set_render_draw_blend_mode r Sdl.Blend.mode_blend);
  ignore (Sdl.set_render_draw_color r 0 0 0 160);
  sdl_err (Sdl.render_fill_rect r (Some backdrop));
  ignore (Sdl.set_render_draw_blend_mode r Sdl.Blend.mode_none);
  (* modal panel *)
  fill_rect r ~x:g.mx ~y:g.my ~w:g.mw ~h:g.mh c_pane_bg;
  stroke_rect r ~x:g.mx ~y:g.my ~w:g.mw ~h:g.mh c_border;
  (* top bar *)
  fill_rect r ~x:(g.mx+1) ~y:(g.my+1) ~w:(g.mw-2) ~h:(g.topbar_h-2) c_header_bg;
  draw_string r (g.mx + 10) (g.my + 8) "File Browser" c_accent;
  draw_string_clipped r (g.mx + 10) (g.my + 34) (g.mw - 100) fb.dir c_muted;
  layout_fb_buttons g;
  (* close button *)
  let hov = (Some fb_close_btn == !mouse_over_btn) in
  fill_rect r ~x:fb_close_btn.bx ~y:fb_close_btn.by
    ~w:fb_close_btn.bw ~h:fb_close_btn.bh
    (if hov then c_btn_bg_hov else c_btn_bg);
  stroke_rect r ~x:fb_close_btn.bx ~y:fb_close_btn.by
    ~w:fb_close_btn.bw ~h:fb_close_btn.bh c_btn_border;
  let tx = fb_close_btn.bx + (fb_close_btn.bw - 5*cell_w) / 2 in
  let ty = fb_close_btn.by + (fb_close_btn.bh - cell_h) / 2 in
  draw_string r tx ty fb_close_btn.blabel c_btn_fg;
  (* entry list *)
  fill_rect r ~x:(g.mx+1) ~y:g.list_y ~w:(g.mw-2) ~h:g.list_h c_dark_bg;
  if fb.error <> "" then
    draw_string_clipped r (g.mx + 10) (g.list_y + 8) (g.mw - 20)
      ("[error] " ^ fb.error) c_err
  else begin
    let rec take k = function
      | _ when k = 0 -> []
      | [] -> []
      | x :: xs -> x :: take (k-1) xs
    in
    let drop n lst =
      let rec go n = function
        | xs when n <= 0 -> xs
        | [] -> []
        | _ :: xs -> go (n-1) xs
      in go n lst
    in
    let visible = take g.max_rows (drop fb.scroll fb.entries) in
    List.iteri (fun i e ->
      let idx = fb.scroll + i in
      let ry = g.list_y + i * g.row_h in
      let hov = idx = fb.hover in
      if hov then
        fill_rect r ~x:(g.mx+2) ~y:ry ~w:(g.mw-4) ~h:g.row_h c_selbg;
      let label, color =
        match e with
        | FBParent -> "..", c_muted
        | FBDir n  -> ("[ " ^ n ^ " /]"), c_accent
        | FBFile n -> ("  " ^ n), c_fg
      in
      let action_hint =
        match e with
        | FBFile n ->
            let low = String.lowercase_ascii n in
            if Filename.check_suffix low ".bat" then "script"
            else if Filename.check_suffix low ".abcl" then "load"
            else ""
        | _ -> ""
      in
      draw_string_clipped r (g.mx + 14) (ry + 3)
        (g.mw - 120) label color;
      if action_hint <> "" then
        draw_string r (g.mx + g.mw - 80) (ry + 3)
          (Printf.sprintf "[%s]" action_hint) c_muted
    ) visible
  end;
  (* Filter buttons *)
  let draw_f_btn b label active =
    let hov = (Some b == !mouse_over_btn) in
    let bgc =
      if active then c_btn_file
      else if hov then c_btn_bg_hov else c_btn_bg
    in
    fill_rect r ~x:b.bx ~y:b.by ~w:b.bw ~h:b.bh bgc;
    stroke_rect r ~x:b.bx ~y:b.by ~w:b.bw ~h:b.bh c_btn_border;
    let tx = b.bx + (b.bw - String.length label * cell_w) / 2 in
    let ty = b.by + (b.bh - cell_h) / 2 in
    draw_string r tx ty label c_btn_fg
  in
  draw_f_btn fb_bat_btn  ".bat"  (fb.ext = "bat");
  draw_f_btn fb_abcl_btn ".abcl" (fb.ext = "abcl");
  draw_f_btn fb_all_btn  "Both"  (fb.ext = "");
  (* Scroll hint *)
  let hint = Printf.sprintf "%d/%d  (↑↓/wheel=scroll  Enter=open  Esc=close)"
    (min fb.scroll (List.length fb.entries))
    (List.length fb.entries)
  in
  draw_string r (g.mx + g.mw / 2 - 50)
    (g.my + g.mh - 28) hint c_muted

let redraw renderer =
  relayout ();
  set_color renderer c_bg;
  sdl_err (Sdl.render_clear renderer);
  draw_header renderer;
  draw_toolbar renderer;
  draw_output renderer;
  draw_source renderer;
  draw_actors renderer;
  draw_input renderer;
  draw_status renderer;
  if fb.visible then draw_fb renderer;
  Sdl.render_present renderer

(* ================================================================== *)
(*                           Input handling                            *)
(* ================================================================== *)

let next_actor_cycle () =
  let names = ref [] in
  Eval_thread.iter_actor_table (fun a _ -> names := a :: !names);
  let names = List.sort compare !names in
  match names with
  | [] -> ()
  | _ ->
      let next =
        match !selected_actor with
        | None -> List.hd names
        | Some cur ->
            let rec find = function
              | [] -> List.hd names
              | [_] -> List.hd names
              | a :: b :: _ when a = cur -> b
              | _ :: rest -> find rest
            in
            find names
      in
      do_pprint next

let esc_double_press = ref 0.0

let double_esc_within = 0.7

let handle_text_input s =
  (* Ignore stray text-input events while the File Browser modal is open —
     otherwise typed characters silently pile up behind the modal. *)
  if fb.visible then ()
  else begin
    let cur = !input_cursor in
    let all = current_input () in
    let s' = String.sub all 0 cur ^ s ^ String.sub all cur (String.length all - cur) in
    set_input s';
    input_cursor := cur + String.length s;
    dirty := true
  end

let handle_key_down keycode keymod =
  let open Sdl.K in
  let ctrl = (keymod land Sdl.Kmod.ctrl) <> 0 in
  ignore ctrl;
  (* File browser has its own key handling when visible. *)
  if fb.visible then begin
    if keycode = escape then (fb.visible <- false; dirty := true)
    else if keycode = return || keycode = return2 || keycode = kp_enter then begin
      if fb.hover >= 0 && fb.hover < List.length fb.entries then
        fb_open_entry (List.nth fb.entries fb.hover)
    end
    else if keycode = up then begin
      if fb.hover > 0 then fb.hover <- fb.hover - 1
      else if fb.entries <> [] then fb.hover <- 0;
      if fb.hover < fb.scroll then fb.scroll <- fb.hover;
      dirty := true
    end
    else if keycode = down then begin
      let n = List.length fb.entries in
      if fb.hover < n - 1 then fb.hover <- fb.hover + 1
      else if n > 0 then fb.hover <- n - 1;
      let g = modal_geom () in
      if fb.hover >= fb.scroll + g.max_rows then
        fb.scroll <- fb.hover - g.max_rows + 1;
      dirty := true
    end
    else if keycode = pageup then begin
      let g = modal_geom () in
      fb.scroll <- max 0 (fb.scroll - g.max_rows);
      dirty := true
    end
    else if keycode = pagedown then begin
      let g = modal_geom () in
      let max_s = max 0 (List.length fb.entries - g.max_rows) in
      fb.scroll <- min max_s (fb.scroll + g.max_rows);
      dirty := true
    end
    else ()  (* swallow other keys while modal open *)
  end
  else if keycode = return || keycode = return2 || keycode = kp_enter then begin
    let line = current_input () in
    push_history line;
    history_pos := -1;
    set_input "";
    if not (process_command line) then quit_requested := true;
    dirty := true
  end
  else if keycode = backspace then begin
    let s = current_input () in
    let n = String.length s in
    if !input_cursor > 0 && n > 0 then begin
      let s' = String.sub s 0 (!input_cursor - 1)
               ^ String.sub s !input_cursor (n - !input_cursor) in
      let new_cur = !input_cursor - 1 in
      set_input s';
      input_cursor := new_cur;
      dirty := true
    end
  end
  else if keycode = left then begin
    if !input_cursor > 0 then (decr input_cursor; dirty := true)
  end
  else if keycode = right then begin
    if !input_cursor < Buffer.length input_buf then
      (incr input_cursor; dirty := true)
  end
  else if keycode = home then (input_cursor := 0; dirty := true)
  else if keycode = kend  then (input_cursor := Buffer.length input_buf; dirty := true)
  else if keycode = up then begin
    if !history_count > 0 then begin
      let new_pos =
        if !history_pos < 0 then !history_count - 1
        else max 0 (!history_pos - 1)
      in
      history_pos := new_pos;
      set_input history.(new_pos);
      dirty := true
    end
  end
  else if keycode = down then begin
    if !history_count > 0 && !history_pos >= 0 then begin
      if !history_pos >= !history_count - 1 then begin
        history_pos := -1; set_input ""; dirty := true
      end else begin
        incr history_pos;
        set_input history.(!history_pos);
        dirty := true
      end
    end
  end
  else if keycode = pageup then
    (output_scroll := !output_scroll + 5; dirty := true)
  else if keycode = pagedown then
    (output_scroll := max 0 (!output_scroll - 5); dirty := true)
  else if keycode = tab then (next_actor_cycle (); dirty := true)
  else if keycode = f1 then (cmd_help (); dirty := true)
  else if keycode = f2 then (run_compile (); dirty := true)
  else if keycode = f5 then dirty := true
  else if keycode = f10 then quit_requested := true
  else if keycode = escape then begin
    let now = Unix.gettimeofday () in
    if now -. !esc_double_press < double_esc_within then
      quit_requested := true
    else begin
      esc_double_press := now;
      set_input ""; dirty := true;
      status_msg := "Esc でキャンセル（もう一度 Esc で終了）"
    end
  end

let handle_mouse_motion mx my =
  mouse_x := mx; mouse_y := my;
  (* toolbar buttons *)
  let prev_btn = !mouse_over_btn in
  let prev_act = !mouse_over_actor in
  mouse_over_btn := None;
  mouse_over_actor := None;
  List.iter (fun b ->
    if hit_button b mx my then mouse_over_btn := Some b
  ) !buttons;
  if fb.visible then begin
    if hit_button fb_close_btn mx my then mouse_over_btn := Some fb_close_btn;
    if hit_button fb_bat_btn   mx my then mouse_over_btn := Some fb_bat_btn;
    if hit_button fb_abcl_btn  mx my then mouse_over_btn := Some fb_abcl_btn;
    if hit_button fb_all_btn   mx my then mouse_over_btn := Some fb_all_btn;
    (* list hover *)
    let g = modal_geom () in
    let new_hover = ref (-1) in
    if mx >= g.mx && mx < g.mx + g.mw && my >= g.list_y && my < g.list_y + g.list_h then begin
      let row = (my - g.list_y) / g.row_h in
      let idx = fb.scroll + row in
      if idx >= 0 && idx < List.length fb.entries then new_hover := idx
    end;
    if !new_hover <> fb.hover then begin
      fb.hover <- !new_hover;
      dirty := true
    end
  end else begin
    (* actor row hover *)
    List.iter (fun (name, y_top, y_bot) ->
      if mx >= p_actors.px && mx < p_actors.px + p_actors.pw
         && my >= y_top && my < y_bot then
        mouse_over_actor := Some name
    ) !actor_hit_rows
  end;
  if prev_btn != !mouse_over_btn then dirty := true;
  if prev_act <> !mouse_over_actor then dirty := true

let handle_mouse_click mx my =
  if fb.visible then begin
    if hit_button fb_close_btn mx my then begin
      fb.visible <- false; dirty := true
    end
    else if hit_button fb_bat_btn mx my then begin
      fb.ext <- "bat"; fb_load ()
    end
    else if hit_button fb_abcl_btn mx my then begin
      fb.ext <- "abcl"; fb_load ()
    end
    else if hit_button fb_all_btn mx my then begin
      fb.ext <- ""; fb_load ()
    end
    else begin
      let g = modal_geom () in
      if mx >= g.mx && mx < g.mx + g.mw && my >= g.list_y && my < g.list_y + g.list_h then begin
        let row = (my - g.list_y) / g.row_h in
        let idx = fb.scroll + row in
        if idx >= 0 && idx < List.length fb.entries then
          fb_open_entry (List.nth fb.entries idx)
      end
    end
  end else begin
    let hit = ref None in
    List.iter (fun b ->
      if hit_button b mx my then hit := Some b
    ) !buttons;
    (match !hit with
     | Some b -> b.baction (); dirty := true
     | None ->
         (* try actor row click *)
         List.iter (fun (name, y_top, y_bot) ->
           if mx >= p_actors.px && mx < p_actors.px + p_actors.pw
              && my >= y_top && my < y_bot then begin
             do_pprint name;
             dirty := true
           end
         ) !actor_hit_rows)
  end

let point_in_pane (p:pane) mx my =
  mx >= p.px && mx < p.px + p.pw && my >= p.py && my < p.py + p.ph

let handle_mouse_wheel dy =
  if fb.visible then begin
    fb.scroll <- max 0 (fb.scroll - dy * 3);
    let max_s = max 0 (List.length fb.entries - 1) in
    if fb.scroll > max_s then fb.scroll <- max_s;
    dirty := true
  end else if point_in_pane p_source !mouse_x !mouse_y then begin
    loaded_src_scroll := max 0 (!loaded_src_scroll - dy * 3);
    dirty := true
  end else begin
    output_scroll := max 0 (!output_scroll + dy * 2);
    dirty := true
  end

let event = Sdl.Event.create ()

let poll_events () =
  while Sdl.poll_event (Some event) do
    let typ = Sdl.Event.(enum (get event typ)) in
    match typ with
    | `Quit -> quit_requested := true
    | `Window_event ->
        let id = Sdl.Event.(get event window_event_id) in
        if id = Sdl.Event.window_event_resized
           || id = Sdl.Event.window_event_size_changed
           || id = Sdl.Event.window_event_exposed then begin
          (* Force recomputation of pane layout on the next redraw. *)
          dirty := true;
          (* Toolbar button positions must be recomputed so mouse hit tests
             match the newly sized window. *)
          relayout ()
        end
    | `Key_down ->
        let keycode = Sdl.Event.(get event keyboard_keycode) in
        let keymod  = Sdl.Event.(get event keyboard_keymod)  in
        handle_key_down keycode keymod
    | `Text_input ->
        let txt = Sdl.Event.(get event text_input_text) in
        handle_text_input txt
    | `Mouse_motion ->
        let mx = Sdl.Event.(get event mouse_motion_x) in
        let my = Sdl.Event.(get event mouse_motion_y) in
        handle_mouse_motion mx my
    | `Mouse_button_down ->
        let btn = Sdl.Event.(get event mouse_button_button) in
        let mx  = Sdl.Event.(get event mouse_button_x) in
        let my  = Sdl.Event.(get event mouse_button_y) in
        if btn = Sdl.Button.left then handle_mouse_click mx my
    | `Mouse_wheel ->
        let dy = Sdl.Event.(get event mouse_wheel_y) in
        handle_mouse_wheel dy
    | _ -> ()
  done

(* ================================================================== *)
(*                              Main                                   *)
(* ================================================================== *)

let auto_refresh_every = 0.4
let last_auto = ref 0.0

let () =
  start_stdio_capture ();

  sdl_err (Sdl.init Sdl.Init.(video + events));
  ignore (Sdl.set_hint Sdl.Hint.render_vsync "1");
  (* Deliberately NOT using allow_highdpi: we want the framebuffer and the
     logical window size to match so our drawing coordinates and the mouse
     event coordinates live on the same grid. *)
  let win =
    sdl_err (Sdl.create_window ~w:win_w_init ~h:win_h_init
               "AIPL GUI IDE"
               Sdl.Window.(shown + resizable))
  in
  let r =
    sdl_err (Sdl.create_renderer win ~index:(-1)
               ~flags:Sdl.Renderer.(accelerated + presentvsync))
  in
  Sdl.start_text_input ();
  refresh_window_size ~renderer:(Some r) win;

  (* Register helpful prims (copy of small subset from repl_thread). *)
  Eval_thread.add_prim "array_empty" (function
    | [] -> Eval_thread.make_array [||]
    | _  -> failwith "array_empty(): arity 0 expected");
  Eval_thread.add_prim "spawn" (function
    | [VString cls; VString a] ->
        Eval_thread.spawn_actor ~class_name:cls ~actor_name:a; VUnit
    | _ -> failwith "spawn(class, name)");
  Eval_thread.add_prim "reply" (function
    | [v] ->
        let s = Eval_thread.string_of_value v in
        glog (Printf.sprintf "[REPLY] value=%s" s);
        VUnit
    | _ -> failwith "reply(x): arity 1 expected");

  (* Toolbar buttons: File menu + quick-launch for common demos *)
  let run_script script_path () =
    glog ("[toolbar] script " ^ script_path);
    ignore (process_command ("script " ^ script_path))
  in
  let run_external shell_path () =
    glog ("[toolbar] launching " ^ shell_path);
    try
      let devnull_in = Unix.openfile "/dev/null" [Unix.O_RDONLY] 0 in
      let pid =
        Unix.create_process shell_path [| shell_path |]
          devnull_in Unix.stdout Unix.stderr
      in
      Unix.close devnull_in;
      glog (Printf.sprintf "[toolbar] pid=%d %s" pid shell_path)
    with exn ->
      glog ("[toolbar] failed to launch " ^ shell_path
            ^ ": " ^ Printexc.to_string exn)
  in
  buttons := [
    make_btn "File"          (fun () -> fb_open ());
    make_btn "PingPong"      (run_script "abclc/run_pingpong.bat");
    make_btn "Rotate4Lines"  (run_script "abclc/com04.bat");
    make_btn "Philosophers5" (run_external "./run_philosophers.sh");
    make_btn "BoundedBuffer" (run_external "./run_bounded_buffer_visual.sh");
    make_btn "Compile"       (fun () -> run_compile ());
    make_btn "Kill"          (fun () -> ignore (process_command "kill"));
    make_btn "Clear"         (fun () -> clear_output ());
  ];

  glog "[gui] AIPL GUI IDE 起動。F1=help  F2=compile  F10=quit";
  glog "[gui] 上のツールバーからデモを起動、File からファイル選択";

  let running = ref true in
  while !running do
    refresh_window_size ~renderer:(Some r) win;
    (* Also update if user resized — allow_highdpi means we sometimes need
       to query both drawable and window size. *)
    poll_events ();
    let now = Unix.gettimeofday () in
    if now -. !last_auto >= auto_refresh_every then begin
      last_auto := now;
      dirty := true
    end;
    if !dirty then begin
      redraw r;
      dirty := false
    end;
    if !quit_requested then running := false;
    Sdl.delay 16l
  done;

  (try Sdl.stop_text_input () with _ -> ());
  Sdl.destroy_renderer r;
  Sdl.destroy_window win;
  Sdl.quit ();
  exit 0
