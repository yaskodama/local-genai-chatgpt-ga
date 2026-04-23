{
  open Lexing
  open Parser

  let newline lb =
    lb.lex_curr_p <- { lb.lex_curr_p with
      pos_lnum = lb.lex_curr_p.pos_lnum + 1;
      pos_bol  = lb.lex_curr_p.pos_cnum;
    }
}

rule token = parse
  (* --- 行コメント：// ... 改行/EOF まで捨てる --- *)
| "//" [^ '\n' '\r']* ("\r"? "\n")   { newline lexbuf; token lexbuf }
| "//" [^ '\n' '\r']* eof           { EOF }  (* そのまま EOF を返す or token lexbuf でも可 *)

  (* --- ブロックコメント：/* ... */（入れ子なし） --- *)
| "/*"                              { block_comment lexbuf; token lexbuf }

  (* 改行：行番号を進める *)
| '\r' '\n'                         { newline lexbuf; token lexbuf }  (* CRLF *)
| '\n'                              { newline lexbuf; token lexbuf }
| '\r'                              { newline lexbuf; token lexbuf }

  (* 空白スキップ：※ 改行は含めないこと！ *)
| [' ' '\t']+                       { token lexbuf }

  (* --- キーワード/記号 --- *)
| "class"      { CLASS }
| "become"     { BECOME }
| "method"     { METHOD }
| "float"      { FLOAT }
| "call"       { CALL }
| "send!"      { UNSAFESEND }
| "send"       { SEND }
| "if"         { IF }
| "self"       { SELF }
| "sender"     { SENDER }
| "then"       { THEN }
| "else"       { ELSE }
| "while"      { WHILE }
| "do"         { DO }
| "select"     { SELECT }
| "case"       { CASE }
| "timeout"    { TIMEOUT }
| "->"         { ARROW }
| "=="         { EQ }
| "!="         { NEQ }
| ">="         { GE }
| "<="         { LE }
| ">"          { GT }
| "<"          { LT }
| "="          { ASSIGN }
| "+"          { PLUS }
| "-"          { MINUS }
| "*"          { TIMES }
| "/"          { DIV }
| "("          { LPAREN }
| ")"          { RPAREN }
| "{"          { LBRACE }
| "}"          { RBRACE }
| ";"          { SEMICOLON }
| ","          { COMMA }
| "."          { DOT }
| "var"        { VAR }
| "new"        { NEW }
| "class"      { CLASS }
| "remote"     { REMOTE }

  (* --- リテラル/識別子 --- *)
(* 1. 「100.5」形式（整数部・小数部あり） *)
| ['0'-'9']+ '.' ['0'-'9']+ as num { FLOATLIT (float_of_string num) }
(* 2. 「100.」形式（整数部＋ドットだけでも float として認識） *)
| ['0'-'9']+ '.' as num             { FLOATLIT (float_of_string (num ^ "0")) }
(* 3. 「100」形式（整数） *)
| ['0'-'9']+ as num                 { INTLIT (int_of_string num) }
| '"' ([^ '"' '\\'] | '\\' ['\\' '"' 'n' 't' 'r'] )* '"' as lit {
    let s = String.sub lit 1 (String.length lit - 2)
    in
    STRINGLIT s
}
| ['a'-'z' 'A'-'Z' '_']['a'-'z' 'A'-'Z' '0'-'9' '_']* as id { ID id }

  (* 入力終端 *)
| eof                               { EOF }

and block_comment = parse
  | "*/"                            { () }
  | '\r' '\n'                       { newline lexbuf; block_comment lexbuf }
  | '\n'                            { newline lexbuf; block_comment lexbuf }
  | '\r'                            { newline lexbuf; block_comment lexbuf }
  | _                               { block_comment lexbuf }
  | eof                             {
                                      let p = lexbuf.lex_curr_p in
                                      failwith (Printf.sprintf
                                        "unterminated block comment at line %d, col %d"
                                        p.pos_lnum (p.pos_cnum - p.pos_bol + 1))
                                    }
