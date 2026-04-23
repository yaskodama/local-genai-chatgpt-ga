type t = {
    line : int;
    col : int;
}

let dummy = { line = 0; col = 0 }

let to_string (loc : t) =
  if loc.line <= 0 then "(unknown location)"
  else Printf.sprintf "line %d, col %d" loc.line loc.col
