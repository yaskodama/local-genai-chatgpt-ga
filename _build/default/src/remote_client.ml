open Unix
open Ast

let json_of_expr e =
  match e.desc with
  | Int i -> string_of_int i
  | Float f -> string_of_float f
  | String s -> Printf.sprintf "%S" s
  | _ -> failwith "remote_send: unsupported expr"

let resolve_host h =
  try Unix.inet_addr_of_string h
  with _ ->
    (Unix.gethostbyname h).Unix.h_addr_list.(0)

let remote_send ~hostport ~to_actor ~meth ~args ~from =
  let host, port =
    match String.split_on_char ':' hostport with
    | [h; p] -> (h, int_of_string p)
    | [h] -> (h, 8080)
    | _ -> failwith ("bad hostport: " ^ hostport)
  in
  let body =
    Printf.sprintf
      {|{"to":%S,"method":%S,"args":[%s],"from":%S}|}
      to_actor
      meth
      (String.concat "," (List.map json_of_expr args))
      from
  in
 let addr = Unix.ADDR_INET (resolve_host host, port) in
  let sock = Unix.socket Unix.PF_INET Unix.SOCK_STREAM 0 in
  Unix.connect sock addr;
  let oc = Unix.out_channel_of_descr sock in
  let ic = Unix.in_channel_of_descr sock in
  Printf.fprintf oc "POST /api/json/send HTTP/1.1\r\n";
  Printf.fprintf oc "Host: %s\r\n" hostport;
  Printf.fprintf oc "Content-Type: application/json\r\n";
  Printf.fprintf oc "Content-Length: %d\r\n" (String.length body);
  Printf.fprintf oc "Connection: close\r\n";
  Printf.fprintf oc "\r\n";
  output_string oc body;
  flush oc;
  (try while true do ignore (input_line ic) done with End_of_file -> ());
  close_in_noerr ic;
  close_out_noerr oc
