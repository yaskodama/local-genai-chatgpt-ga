(* abcl2c.ml — ABCL/c+ ソースを C に変換 *)

let usage () =
  prerr_endline "usage: abcl2c <input.abcl> [-o <output>] [--max-msgs N] [--xinu | --python]";
  exit 1

let () =
  let input  = ref None in
  let output = ref None in
  let max_msgs = ref 12 in
  let xinu = ref false in
  let py = ref false in
  let args = Array.to_list Sys.argv |> List.tl in
  let rec loop = function
    | [] -> ()
    | "-o" :: f :: rest -> output := Some f; loop rest
    | "--max-msgs" :: n :: rest -> max_msgs := int_of_string n; loop rest
    | "--xinu" :: rest -> xinu := true; loop rest
    | "--python" :: rest -> py := true; loop rest
    | "-h" :: _ | "--help" :: _ -> usage ()
    | f :: rest when !input = None -> input := Some f; loop rest
    | x :: _ -> Printf.eprintf "unknown arg: %s\n" x; usage ()
  in
  loop args;
  let input = match !input with Some f -> f | None -> usage () in
  let default_ext = if !py then ".py" else ".c" in
  let output =
    match !output with
    | Some f -> f
    | None -> (Filename.remove_extension input) ^ default_ext
  in
  let ic = open_in input in
  let lexbuf = Lexing.from_channel ic in
  let prog =
    try Parser.program Lexer.token lexbuf
    with e ->
      close_in_noerr ic;
      Printf.eprintf "parse error in %s: %s\n" input (Printexc.to_string e);
      exit 2
  in
  close_in ic;
  let c_code =
    if !py        then C_translator.gen_program_python ~max_messages:!max_msgs prog
    else if !xinu then C_translator.gen_program_xinu   ~max_messages:!max_msgs prog
    else               C_translator.gen_program        ~max_messages:!max_msgs prog
  in
  let oc = open_out output in
  output_string oc c_code;
  close_out oc;
  Printf.printf "wrote %s\n" output
