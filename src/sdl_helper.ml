(* sdl_helper.ml *)
open Tsdl

type cmd =
  | Init of int * int * string
  | Line of int * int * int * int
  | LineRGB of int * int * int * int * int * int * int
      (* x1 y1 x2 y2  r g b *)
  | Clear
  | Present
  | Quit
  | EraseLine of int * int * int * int

let q = Queue.create ()
let m = Mutex.create ()
let c = Condition.create ()
let running = ref true
let log s = prerr_endline ("[SDL] " ^ s)
let post cmd =
  Mutex.lock m; Queue.add cmd q; Condition.signal c; Mutex.unlock m
(*   log "posted cmd"    *)

(* Non-blocking keyboard event queue. KeyDown scancodes are enqueued by
   the SDL main thread and drained by `sdl_poll_key` from ABCL actors. *)
let key_q : int Queue.t = Queue.create ()
let key_m = Mutex.create ()
let sdl_poll_key () : int =
  Mutex.lock key_m;
  let r = if Queue.is_empty key_q then 0 else Queue.pop key_q in
  Mutex.unlock key_m;
  r

(* Latest mouse state, updated by the SDL main thread from
   Mouse_button_down / Mouse_button_up / Mouse_motion events.
   sdl_mouse_down returns 1 while the left button is held. *)
let mouse_x    = ref 0
let mouse_y    = ref 0
let mouse_down = ref 0
let mouse_m    = Mutex.create ()

let sdl_mouse_x () : int =
  Mutex.lock mouse_m; let r = !mouse_x in Mutex.unlock mouse_m; r
let sdl_mouse_y () : int =
  Mutex.lock mouse_m; let r = !mouse_y in Mutex.unlock mouse_m; r
let sdl_mouse_down () : int =
  Mutex.lock mouse_m; let r = !mouse_down in Mutex.unlock mouse_m; r

(* 外部公開 API：他スレッドからはこれだけ呼ぶ *)
let sdl_init ~w ~h ~title = post (Init (w,h,title))
let sdl_draw_line x1 y1 x2 y2 = post (Line (x1,y1,x2,y2))
let sdl_draw_line_rgb x1 y1 x2 y2 r g b = post (LineRGB (x1,y1,x2,y2,r,g,b))
let sdl_clear () = post Clear
let sdl_present () = post Present
let sdl_quit () = post Quit
let sdl_erase_line x1 y1 x2 y2 = post (EraseLine (x1, y1, x2, y2))

let self_test_boot () =
  log "self_test_boot: posting Init/Clear/Present";
  post (Init (640, 480, "SelfTest"));
  post Clear;
  post Present

let ev = Sdl.Event.create ()

let rec idle () =
  ignore (Sdl.poll_event (Some ev));
  (match Sdl.Event.(enum (get ev typ)) with
   | `Quit -> running := false
   | _ -> ());
  if Queue.is_empty q && !running then (Sdl.delay 5l; idle ())

let ev = Sdl.Event.create ()

let main_loop () =
(*  log "main_loop: started on main thread"; *)
  let window   = ref None in
  let renderer = ref None in

  let rec loop () =
    (* 1) イベントを1つ捌く（macOSでは必須） *)
    ignore (Sdl.poll_event (Some ev));
    (match Sdl.Event.(enum (get ev typ)) with
     | `Quit -> running := false
     | `Key_down ->
         let sc = Sdl.Event.(get ev keyboard_scancode) in
         Mutex.lock key_m; Queue.add sc key_q; Mutex.unlock key_m
     | `Mouse_button_down ->
         let btn = Sdl.Event.(get ev mouse_button_button) in
         let x   = Sdl.Event.(get ev mouse_button_x) in
         let y   = Sdl.Event.(get ev mouse_button_y) in
         Mutex.lock mouse_m;
         mouse_x := x; mouse_y := y;
         if btn = Sdl.Button.left then mouse_down := 1;
         Mutex.unlock mouse_m
     | `Mouse_button_up ->
         let btn = Sdl.Event.(get ev mouse_button_button) in
         let x   = Sdl.Event.(get ev mouse_button_x) in
         let y   = Sdl.Event.(get ev mouse_button_y) in
         Mutex.lock mouse_m;
         mouse_x := x; mouse_y := y;
         if btn = Sdl.Button.left then mouse_down := 0;
         Mutex.unlock mouse_m
     | `Mouse_motion ->
         let x = Sdl.Event.(get ev mouse_motion_x) in
         let y = Sdl.Event.(get ev mouse_motion_y) in
         Mutex.lock mouse_m;
         mouse_x := x; mouse_y := y;
         Mutex.unlock mouse_m
     | _ -> ());

    if not !running then (
      (* 終了処理 *)
      (match !renderer with Some r -> Sdl.destroy_renderer r | None -> ());
      (match !window   with Some w -> Sdl.destroy_window w   | None -> ());
      Sdl.quit ();
      ()
    ) else (
      (* 2) キューから1件だけ非ブロッキングで取り出す *)
      let cmd_opt =
        Mutex.lock m;
        let res =
          if Queue.is_empty q then None else Some (Queue.take q)
        in
        Mutex.unlock m;
        res
      in
      (* 3) コマンドを処理（なければ小休止） *)
      (match cmd_opt with
       | None ->
           Sdl.delay 5l
       | Some (Init (w,h,title)) ->
(*           log (Printf.sprintf "Init %dx%d %s" w h title);  *)
            (match Sdl.init Sdl.Init.video with
            | Ok () -> ()
            | Error (`Msg e) -> failwith ("Sdl.init failed: " ^ e));
           let flags = Sdl.Window.(shown + allow_highdpi) in
           let win =
             match Sdl.create_window ~w ~h title flags with
             | Ok w -> w
             | Error (`Msg e) -> failwith ("create_window failed: " ^ e)
           in
           (* Init の処理内（renderer 生成前）に追加：VSync を強く要求 *)
           ignore (Sdl.set_hint Sdl.Hint.render_vsync "1");
           (* レンダラ生成を presentvsync 付きにする *)
           let ren =
             match Sdl.create_renderer win ~index:(-1)
               ~flags:Sdl.Renderer.(accelerated + presentvsync) with
             | Ok r -> r
             | Error (`Msg e) -> failwith ("create_renderer failed: " ^ e)
           in
           window := Some win;
           renderer := Some ren;
           ignore (Sdl.raise_window win);                 (* 最前面へ *)
           ignore (Sdl.show_window win);                  (* 明示的に表示 *)
           ignore (Sdl.render_set_logical_size ren w h);  (* 論理サイズ = 640x480 など *)
	   ignore (Sdl.set_render_draw_color ren 0 0 0 255);  (* 背景: 黒 *)
           ignore (Sdl.render_clear ren);
           Sdl.render_present ren;
           ignore (Sdl.set_render_draw_color ren 255 255 255 255)  (* 線: 白 *)
       | Some (Line (x1,y1,x2,y2)) ->
(*           log (Printf.sprintf "Line %d,%d -> %d,%d" x1 y1 x2 y2); *)
           (match !renderer with
            | None -> ()
            | Some r ->
		ignore (Sdl.render_draw_line r x1 y1 x2 y2);
                ignore (Sdl.set_render_draw_color r 255 255 255 255))
       | Some (LineRGB (x1,y1,x2,y2,cr,cg,cb)) ->
           (match !renderer with
            | None -> ()
            | Some r ->
                ignore (Sdl.set_render_draw_color r cr cg cb 255);
                ignore (Sdl.render_draw_line r x1 y1 x2 y2);
                ignore (Sdl.set_render_draw_color r 255 255 255 255))
       | Some Clear ->
(*           log "Clear";    *)
           (match !renderer with
            | None -> ()
            | Some r ->
                ignore (Sdl.set_render_draw_color r 0 0 0 255);
                ignore (Sdl.render_clear r);
                  (* ★ 線色を白に戻すのを忘れない *)
                ignore (Sdl.set_render_draw_color r 255 255 255 255))
       | Some Present ->
(*           log "Present";    *)
           (match !renderer with
            | None -> ()
            | Some r -> Sdl.render_present r)
       | Some (EraseLine (x1,y1,x2,y2)) ->
           (match !renderer with
            | None -> ()
            | Some r ->
              ignore (Sdl.set_render_draw_blend_mode r Sdl.Blend.mode_none);
              ignore (Sdl.set_render_draw_color r 0 0 0 255);
              ignore (Sdl.render_draw_line r x1 y1 x2 y2);
              ignore (Sdl.set_render_draw_color r 255 255 255 255))
       | Some Quit ->
           running := false
      );
      (* 4) 次フレーム *)
      loop ()
    )
  in
  loop ()
