(* ast.ml *)
type expr = {
  loc : Location.t;
  desc : expr_desc;
} and expr_desc =
  | Int of int
  | Float of float
  | String of string
  | Binop of string * expr * expr
  | Call of string * expr list
  | Expr of expr
  | Var of string
  | New of string * expr list    (* new Line(10,20) *)
  | Array of expr list * Types.ty option

type send_target =
  | LocalTarget of string
  | RemoteTarget of string * string

type stmt_desc =
  | Assign of string * expr
  | CallStmt of string * expr list
  | Send of send_target * string * expr list
  | UnsafeSend of send_target * string * expr list
  | Become of string * expr list
  | Seq of stmt list
  | If of expr * stmt * stmt
  | While of expr * stmt
  | VarDecl of string * expr
  | Select of select_case list * (int option * stmt option)
and stmt = {
  sloc : Location.t;
  sdesc : stmt_desc;
}
and select_pat = {
  meth : string;
  vars : string list;
}
and select_case = {
  pat  : select_pat;
  body : stmt;
}

type method_decl = {
   mname : string;
   params : string list;
   body : stmt;
}

type class_decl = {
  cname : string;
  fields : stmt list;
  methods : method_decl list;
}

type decl =
  | Class of class_decl
  | Global of stmt

type program = decl list

let mk_var (x : string) : expr = { loc = Location.dummy; desc = Var x }

let mk_int (n : int) : expr = { loc = Location.dummy; desc = Int n }
let mk_float (f : float) : expr  = { loc = Location.dummy; desc = Float f }
let mk_expr (d : expr_desc) : expr = { loc = Location.dummy; desc = d }
let mk_stmt ?(loc = Location.dummy) (d : stmt_desc) : stmt = { sloc = loc; sdesc = d }
(*
  ========= AST pretty printer =========
  - string_of_expr / string_of_stmt / string_of_decl:
      1行で読みやすい表現
  - dump_*:
      木構造 (├─ / └─) で多段表示。葉は "Float 10.0" のように直接表示。
*)

let rec string_of_expr (e:expr) : string =
  match e.desc with
  | Int i          -> Printf.sprintf "Int %d" i
  | Float f        -> Printf.sprintf "Float %g" f
  | String s       -> Printf.sprintf "String %S" s
  | Binop (op,a,b) -> Printf.sprintf "Binop(%s, %s, %s)" op (string_of_expr a) (string_of_expr b)
  | Call (f,args)  -> let xs = args |> List.map string_of_expr |> String.concat ", " in
      Printf.sprintf "Call(%s, [%s])" f xs
  | Expr e         -> string_of_expr e
  | Var x          -> Printf.sprintf "Var %s" x
  | New (cls, args) -> let xs = args |> List.map string_of_expr |> String.concat ", " in
      Printf.sprintf "New(%s, [%s])" cls xs
  | Array (es, _tyopt) ->
    let xs = es |> List.map string_of_expr |> String.concat ", " in
    Printf.sprintf "Array[%s]" xs

let string_of_send_target = function
  | LocalTarget t -> t
  | RemoteTarget (hp, a) -> "remote(" ^ hp ^ "," ^ a ^ ")"

let rec string_of_stmt (s:stmt) : string =
  match s.sdesc with
  | Assign (x,e)          -> Printf.sprintf "Assign(%s, %s)" x (string_of_expr e)
  | CallStmt (f,args)     -> let xs = args |> List.map string_of_expr |> String.concat ", " in
      Printf.sprintf "CallStmt(%s, [%s])" f xs
  | Send (tgt,meth,args)  -> let xs = args |> List.map string_of_expr |> String.concat ", " in
      Printf.sprintf "Send(%s.%s, [%s])" (string_of_send_target tgt) meth xs
  | UnsafeSend (tgt,meth,args)  -> let xs = args |> List.map string_of_expr |> String.concat ", " in
      Printf.sprintf "UnsafeSend(%s.%s, [%s])" (string_of_send_target tgt) meth xs
  | Become (cls,args) ->  (* ★ 追加 *)
      let xs = args |> List.map string_of_expr |> String.concat ", " in
      Printf.sprintf "Become(%s, [%s])" cls xs
  | Seq ss                -> let xs = ss |> List.map string_of_stmt |> String.concat "; " in
      Printf.sprintf "Seq([%s])" xs
  | If (e,s1,s2)          -> Printf.sprintf "If(%s, %s, %s)" (string_of_expr e) (string_of_stmt s1) (string_of_stmt s2)
  | While (e,body)        -> Printf.sprintf "While(%s, %s)" (string_of_expr e) (string_of_stmt body)
  | VarDecl (e1,e2)       -> Printf.sprintf "VarDecl(%s, %s)" e1 (string_of_expr e2)
  | Select (l1,l2)        -> Printf.sprintf "Select( )"

(* 既存の型に合わせて class/decl まわりも文字列化 *)
(* let string_of_field (name, e) =
  Printf.sprintf "%s=%s" name (string_of_expr e) *)

let string_of_method_decl (md : method_decl) =
  let params = String.concat ", " md.params in
  Printf.sprintf "Method(%s(%s), body=%s)"
    md.mname params (string_of_stmt md.body)

let string_of_class_decl (c : class_decl) =
  let fs = c.fields |> List.map string_of_stmt |> String.concat "; " in
  let ms = c.methods |> List.map string_of_method_decl |> String.concat "; " in
    Printf.sprintf "Class(%s, fields=[%s], methods=[%s])" c.cname fs ms

let string_of_decl = function
  | Class c    -> string_of_class_decl c
  | Global s   -> "Global(" ^ string_of_stmt s ^ ")"

let string_of_program (p : program) =
  p |> List.map string_of_decl |> String.concat "\n"

(* ---------- 木構造ダンプ（├─ / └─） ---------- *)

let label_of_expr (e:expr) : string =
  match e.desc with
  | Int i          -> Printf.sprintf "Int %d" i
  | Float f        -> Printf.sprintf "Float %g" f
  | String s       -> Printf.sprintf "String %S" s
  | Binop (op,_,_) -> "Binop " ^ op
  | Call (f,_)     -> "Call " ^ f
  | Expr _         -> "Expr"
  | Var x          -> "Var " ^ x
  | New (cls, _)   -> "New " ^ cls                 (* ★ 追加 *)
  | Array (_,_)    -> "Array"
;;

let children_of_expr (e:expr) : ('a list) =
  match e.desc with
  | Binop (_,a,b) -> [a; b]
  | Call (_,arg)  -> arg
  | Expr e        -> [e]
  | New (_, args)              -> args                 (* ★ 追加 *)
  | _             -> []

let rec dump_expr ?(prefix="") ?(is_last=true) (e : expr) =
  let branch = if is_last then "└─ " else "├─ " in
  Printf.printf "%s%s%s\n" prefix branch (label_of_expr e);
  let kids = children_of_expr e in
  let child_pref = prefix ^ (if is_last then "   " else "│  ") in
  List.iteri (fun i k ->
    dump_expr ~prefix:child_pref ~is_last:(i = List.length kids - 1) k
  ) kids

let label_of_stmt (s:stmt) : string =
  match s.sdesc with
  | Assign (x,_)         -> "Assign " ^ x
  | CallStmt (f,_)       -> "CallStmt " ^ f
  | Send (LocalTarget t, m, _) -> "Send " ^ t ^ "." ^ m
  | Send (RemoteTarget (hp, a), m, _) -> "Send remote(" ^ hp ^ "," ^ a ^ ")." ^ m
  | UnsafeSend (LocalTarget t, m, _) -> "UnsafeSend " ^ t ^ "." ^ m
  | UnsafeSend (RemoteTarget (hp, a), m, _) -> "UnsafeSend remote(" ^ hp ^ "," ^ a ^ ")." ^ m
  | Become (cls,_)       -> "Become " ^ cls
  | Seq _                -> "Seq"
  | If _                 -> "If"
  | While _              -> "While"
  | VarDecl (x,_)        -> "VarDecl " ^ x
  | Select (_,_)         -> "Select "

let rec dump_stmt ?(prefix="") ?(is_last=true) (s : stmt) =
  let branch = if is_last then "└─ " else "├─ " in
  Printf.printf "%s%s%s\n" prefix branch (label_of_stmt s);
  let child_pref = prefix ^ (if is_last then "   " else "│  ") in
    begin match s.sdesc with
    | Assign (_, e) ->
      dump_expr ~prefix:child_pref ~is_last:true e
    | CallStmt (_f, args) ->
      List.iteri (fun i e -> dump_expr ~prefix:child_pref ~is_last:(i = List.length args - 1) e) args
    | Send (_target,_m,args) ->
      List.iteri (fun i e -> dump_expr ~prefix:child_pref ~is_last:(i = List.length args - 1) e) args
    | UnsafeSend (_target,_m,args) ->
      List.iteri (fun i e -> dump_expr ~prefix:child_pref ~is_last:(i = List.length args - 1) e) args
    | Seq ss ->
      List.iteri (fun i st -> dump_stmt ~prefix:child_pref ~is_last:(i = List.length ss - 1) st) ss
    | Become (_cls, args) ->
      List.iteri (fun i e -> dump_expr ~prefix:child_pref ~is_last:(i = List.length args - 1) e) args
    | If (e, s1, s2) ->
      dump_expr ~prefix:child_pref ~is_last:false e;
      dump_stmt ~prefix:child_pref ~is_last:false s1;
      dump_stmt ~prefix:child_pref ~is_last:true  s2
    | While (e, body) ->
      dump_expr ~prefix:child_pref ~is_last:false e;
      dump_stmt ~prefix:child_pref ~is_last:true  body
    | VarDecl (_x,e) ->
      dump_expr ~prefix:child_pref ~is_last:true e
    | Select (cases, (to_ms_opt, to_body_opt)) ->
      (* children: cases + optional timeout *)
      let n_cases = List.length cases in
      let has_timeout = match to_ms_opt, to_body_opt with Some _, Some _ -> true | _ -> false in
      let n_children = n_cases + (if has_timeout then 1 else 0) in

      let child_is_last i = (i = n_children - 1) in

      (* dump each case *)
      List.iteri (fun i c ->
        let line =
          "case " ^ c.pat.meth ^ "(" ^ String.concat ", " c.pat.vars ^ ")"
        in
        Printf.printf "%s%s%s\n" child_pref (if child_is_last i then "└─ " else "├─ ") line;

        (* case body as a child of the case line *)
	      let case_pref = child_pref ^ (if child_is_last i then "   " else "│  ") in
        dump_stmt ~prefix:case_pref ~is_last:true c.body
      ) cases;

      (* dump timeout if present *)
      (match to_ms_opt, to_body_opt with
       | Some ms, Some tb ->
           let i = n_cases in
           Printf.printf "%s%s%s\n" child_pref (if child_is_last i then "└─ " else "├─ ")
             ("timeout " ^ string_of_int ms);
           let t_pref = child_pref ^ (if child_is_last i then "   " else "│  ") in
           dump_stmt ~prefix:t_pref ~is_last:true tb
       | _ -> ())
end

let dump_decl ?(prefix="") ?(is_last=true) = function
  | Class c ->
      let branch = if is_last then "└─ " else "├─ " in
      Printf.printf "%s%sClass %s\n" prefix branch c.cname;
      let child_pref = prefix ^ (if is_last then "   " else "│  ") in
      (* fields *)
      let n_fields = List.length c.fields in
      if n_fields > 0 then (
        Printf.printf "%s├─ fields\n" child_pref;
        let f_pref = child_pref ^ "│  " in
        List.iteri (fun i st ->
          let lastf = (i = n_fields -1) in
          let branch2 = if lastf then "└─ " else "├─ " in
          match st.sdesc with
          | VarDecl (name, e) ->
            Printf.printf "%s%s%s =\n" f_pref branch2 name;
            let p2 = f_pref ^ (if lastf then "   " else "│  ") in
            dump_expr ~prefix:p2 ~is_last:true e
          | other ->
            Printf.printf "%s%s<field: %s>\n" f_pref branch2 (string_of_stmt (mk_stmt other))
        ) c.fields
      );
      (* methods *)
      let n_methods = List.length c.methods in
      if n_methods > 0 then (
        Printf.printf "%s└─ methods\n" child_pref;
        let m_pref = child_pref ^ "   " in
        List.iteri (fun i md ->
          let lastm = i = n_methods - 1 in
          let branch2 = if lastm then "└─ " else "├─ " in
          let params = String.concat ", " md.params in
          Printf.printf "%s%s%s(%s)\n" m_pref branch2 md.mname params;
          let p2 = m_pref ^ (if lastm then "   " else "│  ") in
          dump_stmt ~prefix:p2 ~is_last:true md.body
        ) c.methods
      )
  | Global s ->                           (* ★ 追加 *)
      let branch = if is_last then "└─ " else "├─ " in
      Printf.printf "%s%sGlobal\n" prefix branch;
      let p = prefix ^ (if is_last then "   " else "│  ") in
        dump_stmt ~prefix:p ~is_last:true s

let dump_program (p : program) =
  List.iteri (fun i d -> dump_decl ~prefix:"" ~is_last:(i = List.length p - 1) d) p

(* ======== pretty printer (ソース再構成) ======== *)

let indent n = String.make (n*2) ' '   (* インデント：スペース2個×レベル *)

let rec pprint_expr ?(lvl=0) (e:expr) : string =
  match e.desc with
  | Int i -> string_of_int i
  | Float f  -> string_of_float f
  | String s -> Printf.sprintf "\"%s\"" s
  | Var x    -> x
  | Binop (op,a,b) ->
      Printf.sprintf "%s %s %s" (pprint_expr ~lvl a) op (pprint_expr ~lvl b)
  | Call (f,args) ->
      Printf.sprintf "%s(%s)" f (String.concat "," (List.map (pprint_expr ~lvl) args))
  | Expr e   -> pprint_expr ~lvl e
  | New (cls,args) ->
      Printf.sprintf "new %s(%s)" cls
        (String.concat ", " (List.map (pprint_expr ~lvl) args))
  | Array (es, _) ->
    "[" ^ String.concat ", " (List.map (pprint_expr ~lvl) es) ^ "]"

let rec pprint_stmt ?(lvl=0) (s:stmt) : string =
  let indent = String.make (lvl*2) ' ' in
  match s.sdesc with
  | Assign (x,e) ->
      Printf.sprintf "%s%s = %s;" indent x (pprint_expr ~lvl e)
  | VarDecl (x,e) ->
      Printf.sprintf "%svar %s = %s;" indent x (pprint_expr ~lvl e)
  | CallStmt (f,args) ->
      Printf.sprintf "%scall %s(%s);" indent f
        (String.concat ", " (List.map (pprint_expr ~lvl) args))
  | Send (tgt,meth,args) ->
      Printf.sprintf "%ssend %s.%s(%s);" indent (string_of_send_target tgt) meth
        (String.concat ", " (List.map (pprint_expr ~lvl) args))
  | UnsafeSend (tgt,meth,args) ->
      Printf.sprintf "%ssend! %s.%s(%s);" indent (string_of_send_target tgt) meth
        (String.concat ", " (List.map (pprint_expr ~lvl) args))
  | Seq ss ->
      String.concat "\n" (List.map (pprint_stmt ~lvl) ss)
  | If (e,s1,s2) ->
      Printf.sprintf "%sif (%s) {\n%s\n%s} else {\n%s\n%s}"
        indent (pprint_expr e)
        (pprint_stmt ~lvl:(lvl+1) s1) indent
        (pprint_stmt ~lvl:(lvl+1) s2) indent
  | While (e,body) ->
      Printf.sprintf "%swhile (%s) {\n%s\n%s}"
        indent (pprint_expr e)
        (pprint_stmt ~lvl:(lvl+1) body) indent
  | Become (cls, args) ->
      Printf.sprintf "%sbecome %s(%s);"
        indent cls
        (String.concat ", " (List.map (pprint_expr ~lvl) args))
  | Select (_cases, (_to_ms_opt, _to_body_opt)) ->
      Printf.sprintf "%sselect { ... }" indent

let pprint_method ?(lvl=0) (m:method_decl) =
  let args = String.concat ", " m.params in
  Printf.sprintf "%smethod %s(%s) {\n%s\n%s}"
    (indent lvl) m.mname args
    (pprint_stmt ~lvl:(lvl+1) m.body)
    (indent lvl)

let pprint_class (c:class_decl) =
  let indent1 = String.make (1*2) ' ' in
  let fields =
    List.map
      (fun (st:stmt) ->
        match st.sdesc with
        | VarDecl (x,e) ->
          Printf.sprintf "%svar %s = %s;" indent1 x (pprint_expr ~lvl:1 e)
      | _ -> ""
      ) c.fields
  in
  let methods = List.map (pprint_method ~lvl:1) c.methods in
  Printf.sprintf "class %s {\n%s\n%s\n}" c.cname
    (String.concat "\n" fields)
    (String.concat "\n" methods)
