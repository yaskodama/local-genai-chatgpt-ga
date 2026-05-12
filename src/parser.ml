type token =
  | ID of (
# 13 "parser.mly"
        string
# 6 "parser.ml"
)
  | FLOATLIT of (
# 14 "parser.mly"
        float
# 11 "parser.ml"
)
  | INTLIT of (
# 15 "parser.mly"
        int
# 16 "parser.ml"
)
  | STRINGLIT of (
# 16 "parser.mly"
        string
# 21 "parser.ml"
)
  | METHOD
  | FLOAT
  | CALL
  | SEND
  | UNSAFESEND
  | REMOTE
  | NOW
  | FUTURE
  | AWAIT
  | IF
  | THEN
  | ELSE
  | WHILE
  | DO
  | ASSIGN
  | PLUS
  | MINUS
  | TIMES
  | DIV
  | LPAREN
  | RPAREN
  | LBRACE
  | RBRACE
  | SEMICOLON
  | COMMA
  | GE
  | LE
  | GT
  | LT
  | SELF
  | SENDER
  | CLASS
  | SELECT
  | CASE
  | TIMEOUT
  | ARROW
  | EOF
  | NEW
  | VAR
  | EQ
  | NEQ
  | DOT
  | BECOME

open Parsing
let _ = parse_error;;
# 2 "parser.mly"
open Ast
open Location
let mk_expr (d : Ast.expr_desc) : Ast.expr = { loc  = Location.dummy; desc  = d }
let mk_stmt (d : Ast.stmt_desc) : Ast.stmt = { sloc = Location.dummy; sdesc = d }
exception Syntax_error of Location.t * string
let loc_of_rhs i =
  let p = Parsing.rhs_start_pos i in
  { line = p.Lexing.pos_lnum; col  = p.Lexing.pos_cnum - p.Lexing.pos_bol + 1 }
let mk_expr1 i d : Ast.expr = { loc = loc_of_rhs i; desc = d }
let mk_stmt1 i d : Ast.stmt = { sloc = loc_of_rhs i; sdesc = d }
# 80 "parser.ml"
let yytransl_const = [|
  261 (* METHOD *);
  262 (* FLOAT *);
  263 (* CALL *);
  264 (* SEND *);
  265 (* UNSAFESEND *);
  266 (* REMOTE *);
  267 (* NOW *);
  268 (* FUTURE *);
  269 (* AWAIT *);
  270 (* IF *);
  271 (* THEN *);
  272 (* ELSE *);
  273 (* WHILE *);
  274 (* DO *);
  275 (* ASSIGN *);
  276 (* PLUS *);
  277 (* MINUS *);
  278 (* TIMES *);
  279 (* DIV *);
  280 (* LPAREN *);
  281 (* RPAREN *);
  282 (* LBRACE *);
  283 (* RBRACE *);
  284 (* SEMICOLON *);
  285 (* COMMA *);
  286 (* GE *);
  287 (* LE *);
  288 (* GT *);
  289 (* LT *);
  290 (* SELF *);
  291 (* SENDER *);
  292 (* CLASS *);
  293 (* SELECT *);
  294 (* CASE *);
  295 (* TIMEOUT *);
  296 (* ARROW *);
    0 (* EOF *);
  297 (* NEW *);
  298 (* VAR *);
  299 (* EQ *);
  300 (* NEQ *);
  301 (* DOT *);
  302 (* BECOME *);
    0|]

let yytransl_block = [|
  257 (* ID *);
  258 (* FLOATLIT *);
  259 (* INTLIT *);
  260 (* STRINGLIT *);
    0|]

let yylhs = "\255\255\
\001\000\001\000\003\000\003\000\003\000\003\000\005\000\005\000\
\004\000\004\000\004\000\004\000\004\000\004\000\004\000\007\000\
\007\000\010\000\010\000\008\000\008\000\011\000\012\000\012\000\
\012\000\002\000\002\000\013\000\013\000\015\000\015\000\014\000\
\014\000\014\000\014\000\014\000\014\000\014\000\014\000\014\000\
\014\000\014\000\014\000\014\000\014\000\014\000\014\000\014\000\
\016\000\016\000\016\000\016\000\018\000\019\000\020\000\020\000\
\021\000\021\000\017\000\017\000\009\000\009\000\022\000\022\000\
\006\000\006\000\006\000\006\000\006\000\006\000\006\000\006\000\
\006\000\006\000\006\000\006\000\006\000\006\000\006\000\006\000\
\006\000\006\000\006\000\006\000\006\000\006\000\000\000"

let yylen = "\002\000\
\002\000\002\000\001\000\002\000\003\000\002\000\001\000\003\000\
\006\000\005\000\005\000\009\000\008\000\008\000\005\000\001\000\
\002\000\005\000\005\000\001\000\002\000\008\000\000\000\001\000\
\003\000\001\000\006\000\001\000\002\000\002\000\000\000\004\000\
\006\000\005\000\008\000\008\000\008\000\008\000\005\000\007\000\
\004\000\003\000\005\000\009\000\005\000\006\000\005\000\005\000\
\002\000\000\000\002\000\000\000\006\000\004\000\001\000\000\000\
\001\000\003\000\006\000\000\000\000\000\001\000\003\000\005\000\
\001\000\001\000\001\000\001\000\001\000\001\000\003\000\003\000\
\003\000\003\000\005\000\004\000\003\000\003\000\003\000\003\000\
\003\000\003\000\003\000\007\000\007\000\002\000\002\000"

let yydefred = "\000\000\
\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\
\087\000\000\000\000\000\002\000\000\000\026\000\000\000\000\000\
\000\000\000\000\000\000\001\000\000\000\006\000\000\000\065\000\
\067\000\066\000\000\000\000\000\000\000\000\000\069\000\070\000\
\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\
\000\000\005\000\000\000\000\000\000\000\000\000\000\000\000\000\
\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\
\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\
\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\
\000\000\000\000\000\000\083\000\000\000\000\000\000\000\000\000\
\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\
\015\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\
\010\000\017\000\021\000\000\000\011\000\076\000\000\000\000\000\
\000\000\000\000\000\000\000\000\000\000\000\000\000\000\009\000\
\000\000\000\000\000\000\075\000\027\000\000\000\000\000\000\000\
\000\000\000\000\000\000\000\000\000\000\000\000\013\000\014\000\
\000\000\000\000\018\000\019\000\000\000\084\000\085\000\025\000\
\000\000\012\000\000\000\000\000\000\000\000\000\000\000\000\000\
\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\
\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\
\000\000\050\000\000\000\000\000\022\000\029\000\000\000\000\000\
\000\000\000\000\000\000\000\000\000\000\000\000\000\000\030\000\
\042\000\000\000\000\000\000\000\032\000\000\000\000\000\000\000\
\000\000\000\000\000\000\000\000\000\000\041\000\000\000\000\000\
\000\000\049\000\000\000\000\000\000\000\000\000\045\000\034\000\
\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\
\000\000\048\000\000\000\043\000\047\000\000\000\033\000\000\000\
\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\
\046\000\000\000\000\000\000\000\000\000\040\000\057\000\000\000\
\000\000\000\000\000\000\000\000\035\000\036\000\037\000\038\000\
\054\000\000\000\000\000\000\000\000\000\058\000\053\000\059\000\
\044\000"

let yydgoto = "\002\000\
\009\000\016\000\010\000\011\000\034\000\035\000\067\000\068\000\
\036\000\069\000\070\000\121\000\149\000\150\000\161\000\178\000\
\193\000\194\000\208\000\232\000\233\000\000\000"

let yysindex = "\014\000\
\009\255\000\000\037\000\014\255\006\255\006\255\038\255\055\255\
\000\000\065\000\072\255\000\000\171\255\000\000\043\255\023\255\
\039\255\059\255\067\255\000\000\054\255\000\000\068\255\000\000\
\000\000\000\000\006\255\006\255\171\255\171\255\000\000\000\000\
\090\255\064\255\111\000\076\255\102\255\106\255\110\255\255\254\
\212\255\000\000\171\255\070\255\080\255\111\000\013\000\119\255\
\171\255\171\255\171\255\171\255\171\255\171\255\171\255\171\255\
\171\255\171\255\171\255\084\255\120\255\124\255\126\255\134\255\
\151\255\156\255\153\255\139\255\000\255\153\255\184\255\211\255\
\142\255\189\255\193\255\000\000\171\255\111\000\166\255\166\255\
\088\255\088\255\111\000\111\000\111\000\111\000\111\000\111\000\
\000\000\196\255\171\255\171\255\179\255\185\255\188\255\194\255\
\000\000\000\000\000\000\187\255\000\000\000\000\198\255\202\255\
\205\255\210\255\227\255\237\255\236\255\171\255\171\255\000\000\
\171\255\171\255\171\255\000\000\000\000\245\255\250\255\235\255\
\240\255\030\000\047\000\255\255\002\000\007\000\000\000\000\000\
\236\255\253\255\000\000\000\000\009\000\000\000\000\000\000\000\
\096\255\000\000\251\254\038\000\042\255\006\255\016\000\171\255\
\096\255\021\000\048\000\053\000\028\000\096\255\171\255\171\255\
\024\000\019\000\020\000\026\000\027\000\171\255\254\255\096\255\
\039\000\000\000\040\000\052\000\000\000\000\000\064\000\056\000\
\152\255\081\000\082\000\087\000\088\000\079\000\096\255\000\000\
\000\000\036\255\216\255\167\255\000\000\070\000\075\000\068\000\
\089\000\090\000\091\000\097\000\096\255\000\000\104\000\103\000\
\093\000\000\000\124\000\096\000\102\000\125\000\000\000\000\000\
\121\000\171\255\171\255\171\255\171\255\135\000\128\000\113\000\
\116\000\000\000\133\000\000\000\000\000\138\000\000\000\136\000\
\143\000\144\000\148\000\096\255\192\000\170\000\178\000\171\255\
\000\000\177\000\179\000\180\000\181\000\000\000\000\000\173\000\
\182\000\096\255\096\255\185\000\000\000\000\000\000\000\000\000\
\000\000\205\000\186\000\187\000\184\000\000\000\000\000\000\000\
\000\000"

let yyrindex = "\000\000\
\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\
\000\000\000\000\215\001\000\000\191\000\000\000\000\000\000\000\
\000\000\000\000\000\000\000\000\217\001\000\000\238\255\000\000\
\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\
\000\000\193\000\239\254\000\000\000\000\000\000\000\000\000\000\
\000\000\000\000\191\000\000\000\000\000\029\255\000\000\000\000\
\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\
\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\
\000\000\000\000\000\000\000\000\214\000\194\000\000\000\000\000\
\000\000\000\000\000\000\000\000\191\000\015\255\160\000\166\000\
\142\000\154\000\099\255\111\255\116\255\220\255\172\000\174\000\
\000\000\000\000\191\000\191\000\000\000\000\000\000\000\000\000\
\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\
\000\000\000\000\000\000\000\000\195\000\000\000\000\000\000\000\
\191\000\191\000\191\000\000\000\000\000\000\000\000\000\197\000\
\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\
\195\000\000\000\000\000\000\000\115\000\000\000\000\000\000\000\
\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\
\196\000\000\000\000\000\000\000\000\000\198\000\000\000\191\000\
\000\000\000\000\000\000\000\000\000\000\000\000\000\000\196\000\
\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\
\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\
\000\000\199\000\000\000\000\000\000\000\000\000\000\000\000\000\
\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\
\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\
\000\000\191\000\191\000\191\000\191\000\052\255\000\000\000\000\
\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\
\000\000\000\000\000\000\000\000\202\000\000\000\000\000\191\000\
\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\
\203\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\
\000\000\000\000\000\000\000\000\115\000\000\000\000\000\000\000\
\000\000"

let yygindex = "\000\000\
\000\000\005\000\025\000\000\000\000\000\228\255\155\001\032\000\
\213\255\000\000\000\000\100\001\109\255\131\255\070\001\000\000\
\000\000\000\000\000\000\000\000\000\000\000\000"

let yytablesize = 486
let yytable = "\073\000\
\046\000\047\000\166\000\064\000\065\000\065\000\014\000\007\000\
\003\000\004\000\017\000\007\000\072\000\151\000\001\000\015\000\
\005\000\006\000\152\000\160\000\078\000\079\000\080\000\081\000\
\082\000\083\000\084\000\085\000\086\000\087\000\088\000\044\000\
\045\000\105\000\160\000\022\000\012\000\013\000\018\000\008\000\
\066\000\066\000\014\000\008\000\007\000\042\000\086\000\107\000\
\108\000\190\000\008\000\015\000\039\000\086\000\004\000\019\000\
\086\000\086\000\039\000\039\000\039\000\005\000\006\000\206\000\
\020\000\039\000\037\000\038\000\039\000\124\000\125\000\126\000\
\004\000\191\000\192\000\154\000\155\000\039\000\039\000\005\000\
\006\000\122\000\123\000\039\000\040\000\041\000\243\000\244\000\
\039\000\007\000\048\000\043\000\049\000\039\000\230\000\008\000\
\139\000\039\000\096\000\021\000\060\000\099\000\140\000\141\000\
\142\000\061\000\062\000\007\000\168\000\143\000\063\000\089\000\
\144\000\008\000\074\000\159\000\077\000\054\000\055\000\056\000\
\057\000\145\000\167\000\077\000\075\000\184\000\077\000\077\000\
\078\000\174\000\058\000\059\000\146\000\079\000\093\000\078\000\
\198\000\147\000\078\000\078\000\079\000\148\000\077\000\079\000\
\079\000\156\000\157\000\091\000\090\000\092\000\196\000\094\000\
\023\000\024\000\025\000\026\000\095\000\064\000\216\000\217\000\
\218\000\219\000\027\000\028\000\029\000\097\000\102\000\023\000\
\024\000\025\000\026\000\023\000\024\000\025\000\026\000\030\000\
\183\000\027\000\028\000\029\000\236\000\027\000\028\000\029\000\
\100\000\031\000\032\000\052\000\053\000\103\000\030\000\197\000\
\033\000\104\000\030\000\054\000\055\000\056\000\057\000\106\000\
\031\000\032\000\109\000\110\000\031\000\032\000\111\000\033\000\
\058\000\059\000\113\000\033\000\023\000\024\000\025\000\026\000\
\023\000\024\000\025\000\026\000\112\000\114\000\027\000\028\000\
\029\000\115\000\027\000\028\000\029\000\116\000\050\000\051\000\
\052\000\053\000\117\000\030\000\120\000\080\000\101\000\030\000\
\054\000\055\000\056\000\057\000\080\000\031\000\032\000\080\000\
\080\000\031\000\032\000\118\000\071\000\058\000\059\000\068\000\
\195\000\068\000\068\000\068\000\068\000\119\000\068\000\129\000\
\130\000\068\000\068\000\068\000\068\000\068\000\068\000\175\000\
\127\000\050\000\051\000\052\000\053\000\128\000\137\000\133\000\
\068\000\068\000\134\000\054\000\055\000\056\000\057\000\135\000\
\050\000\051\000\052\000\053\000\138\000\076\000\153\000\158\000\
\058\000\059\000\054\000\055\000\056\000\057\000\162\000\169\000\
\163\000\050\000\051\000\052\000\053\000\164\000\165\000\058\000\
\059\000\131\000\179\000\054\000\055\000\056\000\057\000\170\000\
\171\000\177\000\050\000\051\000\052\000\053\000\172\000\173\000\
\058\000\059\000\132\000\180\000\054\000\055\000\056\000\057\000\
\182\000\185\000\186\000\050\000\051\000\052\000\053\000\187\000\
\188\000\058\000\059\000\181\000\201\000\054\000\055\000\056\000\
\057\000\199\000\050\000\051\000\052\000\053\000\200\000\189\000\
\207\000\209\000\058\000\059\000\054\000\055\000\056\000\057\000\
\202\000\203\000\204\000\050\000\051\000\052\000\053\000\210\000\
\205\000\058\000\059\000\212\000\211\000\054\000\055\000\056\000\
\057\000\213\000\050\000\051\000\052\000\053\000\075\000\075\000\
\075\000\075\000\058\000\059\000\054\000\055\000\056\000\057\000\
\075\000\075\000\075\000\075\000\215\000\214\000\220\000\221\000\
\222\000\058\000\059\000\223\000\224\000\075\000\075\000\073\000\
\226\000\073\000\073\000\073\000\073\000\225\000\073\000\227\000\
\228\000\073\000\073\000\074\000\229\000\074\000\074\000\074\000\
\074\000\071\000\074\000\071\000\071\000\074\000\074\000\072\000\
\071\000\072\000\072\000\071\000\071\000\081\000\072\000\082\000\
\231\000\072\000\072\000\234\000\081\000\241\000\082\000\081\000\
\081\000\082\000\082\000\235\000\237\000\246\000\238\000\239\000\
\240\000\245\000\242\000\249\000\247\000\248\000\003\000\061\000\
\004\000\062\000\016\000\023\000\020\000\024\000\031\000\098\000\
\028\000\060\000\056\000\055\000\136\000\176\000"

let yycheck = "\043\000\
\029\000\030\000\150\000\005\001\006\001\006\001\001\001\025\001\
\000\001\001\001\006\000\029\001\041\000\019\001\001\000\010\001\
\008\001\009\001\024\001\145\000\049\000\050\000\051\000\052\000\
\053\000\054\000\055\000\056\000\057\000\058\000\059\000\027\000\
\028\000\077\000\160\000\011\000\000\000\024\001\001\001\025\001\
\042\001\042\001\001\001\029\001\036\001\021\000\018\001\091\000\
\092\000\175\000\042\001\010\001\001\001\025\001\001\001\001\001\
\028\001\029\001\007\001\008\001\009\001\008\001\009\001\189\000\
\000\000\014\001\024\001\045\001\017\001\113\000\114\000\115\000\
\001\001\038\001\039\001\034\001\035\001\026\001\027\001\008\001\
\009\001\110\000\111\000\045\001\026\001\019\001\234\000\235\000\
\037\001\036\001\001\001\024\001\029\001\042\001\220\000\042\001\
\001\001\046\001\067\000\028\001\025\001\070\000\007\001\008\001\
\009\001\004\001\001\001\036\001\152\000\014\001\001\001\028\001\
\017\001\042\001\045\001\144\000\018\001\030\001\031\001\032\001\
\033\001\026\001\151\000\025\001\045\001\169\000\028\001\029\001\
\018\001\158\000\043\001\044\001\037\001\018\001\001\001\025\001\
\180\000\042\001\028\001\029\001\025\001\046\001\024\001\028\001\
\029\001\141\000\142\000\024\001\029\001\024\001\179\000\001\001\
\001\001\002\001\003\001\004\001\001\001\005\001\202\000\203\000\
\204\000\205\000\011\001\012\001\013\001\027\001\025\001\001\001\
\002\001\003\001\004\001\001\001\002\001\003\001\004\001\024\001\
\025\001\011\001\012\001\013\001\224\000\011\001\012\001\013\001\
\001\001\034\001\035\001\022\001\023\001\001\001\024\001\025\001\
\041\001\001\001\024\001\030\001\031\001\032\001\033\001\004\001\
\034\001\035\001\024\001\019\001\034\001\035\001\019\001\041\001\
\043\001\044\001\024\001\041\001\001\001\002\001\003\001\004\001\
\001\001\002\001\003\001\004\001\027\001\024\001\011\001\012\001\
\013\001\024\001\011\001\012\001\013\001\025\001\020\001\021\001\
\022\001\023\001\025\001\024\001\001\001\018\001\028\001\024\001\
\030\001\031\001\032\001\033\001\025\001\034\001\035\001\028\001\
\029\001\034\001\035\001\025\001\041\001\043\001\044\001\018\001\
\041\001\020\001\021\001\022\001\023\001\025\001\025\001\029\001\
\025\001\028\001\029\001\030\001\031\001\032\001\033\001\018\001\
\028\001\020\001\021\001\022\001\023\001\028\001\026\001\025\001\
\043\001\044\001\025\001\030\001\031\001\032\001\033\001\025\001\
\020\001\021\001\022\001\023\001\028\001\025\001\001\001\024\001\
\043\001\044\001\030\001\031\001\032\001\033\001\026\001\024\001\
\001\001\020\001\021\001\022\001\023\001\001\001\027\001\043\001\
\044\001\028\001\019\001\030\001\031\001\032\001\033\001\045\001\
\045\001\027\001\020\001\021\001\022\001\023\001\045\001\045\001\
\043\001\044\001\028\001\024\001\030\001\031\001\032\001\033\001\
\025\001\001\001\001\001\020\001\021\001\022\001\023\001\001\001\
\001\001\043\001\044\001\028\001\025\001\030\001\031\001\032\001\
\033\001\028\001\020\001\021\001\022\001\023\001\028\001\025\001\
\001\001\003\001\043\001\044\001\030\001\031\001\032\001\033\001\
\024\001\024\001\024\001\020\001\021\001\022\001\023\001\027\001\
\024\001\043\001\044\001\028\001\001\001\030\001\031\001\032\001\
\033\001\028\001\020\001\021\001\022\001\023\001\020\001\021\001\
\022\001\023\001\043\001\044\001\030\001\031\001\032\001\033\001\
\030\001\031\001\032\001\033\001\028\001\025\001\016\001\024\001\
\040\001\043\001\044\001\040\001\024\001\043\001\044\001\018\001\
\025\001\020\001\021\001\022\001\023\001\028\001\025\001\025\001\
\025\001\028\001\029\001\018\001\025\001\020\001\021\001\022\001\
\023\001\018\001\025\001\020\001\021\001\028\001\029\001\018\001\
\025\001\020\001\021\001\028\001\029\001\018\001\025\001\018\001\
\001\001\028\001\029\001\026\001\025\001\025\001\025\001\028\001\
\029\001\028\001\029\001\026\001\028\001\001\001\028\001\028\001\
\028\001\025\001\029\001\028\001\027\001\027\001\000\000\025\001\
\000\000\025\001\005\001\025\001\027\001\025\001\027\001\069\000\
\027\001\027\001\025\001\025\001\129\000\160\000"

let yynames_const = "\
  METHOD\000\
  FLOAT\000\
  CALL\000\
  SEND\000\
  UNSAFESEND\000\
  REMOTE\000\
  NOW\000\
  FUTURE\000\
  AWAIT\000\
  IF\000\
  THEN\000\
  ELSE\000\
  WHILE\000\
  DO\000\
  ASSIGN\000\
  PLUS\000\
  MINUS\000\
  TIMES\000\
  DIV\000\
  LPAREN\000\
  RPAREN\000\
  LBRACE\000\
  RBRACE\000\
  SEMICOLON\000\
  COMMA\000\
  GE\000\
  LE\000\
  GT\000\
  LT\000\
  SELF\000\
  SENDER\000\
  CLASS\000\
  SELECT\000\
  CASE\000\
  TIMEOUT\000\
  ARROW\000\
  EOF\000\
  NEW\000\
  VAR\000\
  EQ\000\
  NEQ\000\
  DOT\000\
  BECOME\000\
  "

let yynames_block = "\
  ID\000\
  FLOATLIT\000\
  INTLIT\000\
  STRINGLIT\000\
  "

let yyact = [|
  (fun _ -> failwith "parser")
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 1 : 'decls) in
    Obj.repr(
# 34 "parser.mly"
              ( _1 )
# 459 "parser.ml"
               : Ast.program))
; (fun __caml_parser_env ->
    Obj.repr(
# 35 "parser.mly"
              ( raise (Syntax_error (loc_of_rhs 1, "syntax error in program")) )
# 465 "parser.ml"
               : Ast.program))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 0 : 'decl) in
    Obj.repr(
# 38 "parser.mly"
         ( [_1] )
# 472 "parser.ml"
               : 'decls))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 1 : 'decl) in
    Obj.repr(
# 39 "parser.mly"
                   ( [_1] )
# 479 "parser.ml"
               : 'decls))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 2 : 'decl) in
    let _3 = (Parsing.peek_val __caml_parser_env 0 : 'decls) in
    Obj.repr(
# 40 "parser.mly"
                         ( _1 :: _3 )
# 487 "parser.ml"
               : 'decls))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 1 : 'decl) in
    let _2 = (Parsing.peek_val __caml_parser_env 0 : 'decls) in
    Obj.repr(
# 41 "parser.mly"
               ( _1 :: _2 )
# 495 "parser.ml"
               : 'decls))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 0 : 'expr) in
    Obj.repr(
# 44 "parser.mly"
                             ( [_1] )
# 502 "parser.ml"
               : 'arg_list))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 2 : 'arg_list) in
    let _3 = (Parsing.peek_val __caml_parser_env 0 : 'expr) in
    Obj.repr(
# 45 "parser.mly"
                               ( _1 @ [_3] )
# 510 "parser.ml"
               : 'arg_list))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 4 : string) in
    let _4 = (Parsing.peek_val __caml_parser_env 2 : 'fields) in
    let _5 = (Parsing.peek_val __caml_parser_env 1 : 'methods) in
    Obj.repr(
# 48 "parser.mly"
                                           ( Class { cname = _2; fields = _4; methods = _5 } )
# 519 "parser.ml"
               : 'decl))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 3 : string) in
    let _4 = (Parsing.peek_val __caml_parser_env 1 : 'methods) in
    Obj.repr(
# 49 "parser.mly"
                                           ( Class { cname = _2; fields = []; methods = _4 } )
# 527 "parser.ml"
               : 'decl))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 3 : string) in
    let _4 = (Parsing.peek_val __caml_parser_env 1 : 'expr) in
    Obj.repr(
# 50 "parser.mly"
                                           ( Global (mk_stmt1 2 (VarDecl (_2, _4))) )
# 535 "parser.ml"
               : 'decl))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 7 : string) in
    let _5 = (Parsing.peek_val __caml_parser_env 4 : string) in
    let _7 = (Parsing.peek_val __caml_parser_env 2 : 'args) in
    Obj.repr(
# 52 "parser.mly"
    ( Global (mk_stmt1 2 (VarDecl (_2, mk_expr1 4 (New (_5, _7))))) )
# 544 "parser.ml"
               : 'decl))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 6 : Ast.send_target) in
    let _4 = (Parsing.peek_val __caml_parser_env 4 : string) in
    let _6 = (Parsing.peek_val __caml_parser_env 2 : 'args) in
    Obj.repr(
# 53 "parser.mly"
                                                                       ( Global (mk_stmt1 1 (Send (_2, _4, _6))) )
# 553 "parser.ml"
               : 'decl))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 6 : Ast.send_target) in
    let _4 = (Parsing.peek_val __caml_parser_env 4 : string) in
    let _6 = (Parsing.peek_val __caml_parser_env 2 : 'args) in
    Obj.repr(
# 54 "parser.mly"
                                                                       ( Global (mk_stmt1 1 (UnsafeSend (_2, _4, _6))) )
# 562 "parser.ml"
               : 'decl))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 4 : string) in
    let _3 = (Parsing.peek_val __caml_parser_env 2 : 'args) in
    Obj.repr(
# 55 "parser.mly"
                                           ( Global (mk_stmt1 1 (CallStmt (_1, _3))) )
# 570 "parser.ml"
               : 'decl))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 0 : 'field) in
    Obj.repr(
# 58 "parser.mly"
          ( [_1] )
# 577 "parser.ml"
               : 'fields))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 1 : 'field) in
    let _2 = (Parsing.peek_val __caml_parser_env 0 : 'fields) in
    Obj.repr(
# 59 "parser.mly"
                 ( _1 :: _2 )
# 585 "parser.ml"
               : 'fields))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 3 : string) in
    let _4 = (Parsing.peek_val __caml_parser_env 1 : 'expr) in
    Obj.repr(
# 62 "parser.mly"
                                   ( mk_stmt1 2  (VarDecl (_2, _4)) )
# 593 "parser.ml"
               : 'field))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 3 : string) in
    let _4 = (Parsing.peek_val __caml_parser_env 1 : 'expr) in
    Obj.repr(
# 63 "parser.mly"
                                 ( mk_stmt1 2 (VarDecl (_2, _4)) )
# 601 "parser.ml"
               : 'field))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 0 : 'method_decl) in
    Obj.repr(
# 66 "parser.mly"
                ( [_1] )
# 608 "parser.ml"
               : 'methods))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 1 : 'method_decl) in
    let _2 = (Parsing.peek_val __caml_parser_env 0 : 'methods) in
    Obj.repr(
# 67 "parser.mly"
                        ( _1 :: _2 )
# 616 "parser.ml"
               : 'methods))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 6 : string) in
    let _4 = (Parsing.peek_val __caml_parser_env 4 : 'param_list) in
    let _7 = (Parsing.peek_val __caml_parser_env 1 : 'stmts) in
    Obj.repr(
# 71 "parser.mly"
    ( { mname = _2; params = _4; body = mk_stmt1 2 (Seq _7) } )
# 625 "parser.ml"
               : 'method_decl))
; (fun __caml_parser_env ->
    Obj.repr(
# 74 "parser.mly"
       ( [] )
# 631 "parser.ml"
               : 'param_list))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 0 : string) in
    Obj.repr(
# 75 "parser.mly"
       ( [_1] )
# 638 "parser.ml"
               : 'param_list))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 2 : string) in
    let _3 = (Parsing.peek_val __caml_parser_env 0 : 'param_list) in
    Obj.repr(
# 76 "parser.mly"
                        ( _1::_3 )
# 646 "parser.ml"
               : 'param_list))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 0 : string) in
    Obj.repr(
# 79 "parser.mly"
                                                      ( LocalTarget _1 )
# 653 "parser.ml"
               : Ast.send_target))
; (fun __caml_parser_env ->
    let _3 = (Parsing.peek_val __caml_parser_env 3 : string) in
    let _5 = (Parsing.peek_val __caml_parser_env 1 : string) in
    Obj.repr(
# 80 "parser.mly"
                                                      ( RemoteTarget (_3, _5) )
# 661 "parser.ml"
               : Ast.send_target))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 0 : 'stmt) in
    Obj.repr(
# 83 "parser.mly"
         ( [_1] )
# 668 "parser.ml"
               : 'stmts))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 1 : 'stmt) in
    let _2 = (Parsing.peek_val __caml_parser_env 0 : 'stmts) in
    Obj.repr(
# 84 "parser.mly"
               ( _1 :: _2 )
# 676 "parser.ml"
               : 'stmts))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 1 : 'stmt) in
    let _2 = (Parsing.peek_val __caml_parser_env 0 : 'stmt_list) in
    Obj.repr(
# 87 "parser.mly"
                   ( _1::_2 )
# 684 "parser.ml"
               : 'stmt_list))
; (fun __caml_parser_env ->
    Obj.repr(
# 88 "parser.mly"
                   ( [] )
# 690 "parser.ml"
               : 'stmt_list))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 3 : string) in
    let _3 = (Parsing.peek_val __caml_parser_env 1 : 'expr) in
    Obj.repr(
# 91 "parser.mly"
                             ( mk_stmt1 1 (Assign (_1, _3)) )
# 698 "parser.ml"
               : 'stmt))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 4 : string) in
    let _4 = (Parsing.peek_val __caml_parser_env 2 : 'args) in
    Obj.repr(
# 92 "parser.mly"
                                         ( mk_stmt1 2 (CallStmt (_2, _4)) )
# 706 "parser.ml"
               : 'stmt))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 3 : string) in
    Obj.repr(
# 93 "parser.mly"
                                    ( mk_stmt1 2 (CallStmt (_2, [])) )
# 713 "parser.ml"
               : 'stmt))
; (fun __caml_parser_env ->
    let _4 = (Parsing.peek_val __caml_parser_env 4 : string) in
    let _6 = (Parsing.peek_val __caml_parser_env 2 : 'args) in
    Obj.repr(
# 94 "parser.mly"
                                                  ( mk_stmt1 4 (Send(LocalTarget "self", _4, _6)) )
# 721 "parser.ml"
               : 'stmt))
; (fun __caml_parser_env ->
    let _4 = (Parsing.peek_val __caml_parser_env 4 : string) in
    let _6 = (Parsing.peek_val __caml_parser_env 2 : 'args) in
    Obj.repr(
# 95 "parser.mly"
                                                    ( mk_stmt1 4 (Send (LocalTarget "sender", _4, _6)) )
# 729 "parser.ml"
               : 'stmt))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 6 : Ast.send_target) in
    let _4 = (Parsing.peek_val __caml_parser_env 4 : string) in
    let _6 = (Parsing.peek_val __caml_parser_env 2 : 'args) in
    Obj.repr(
# 96 "parser.mly"
                                                         ( mk_stmt1 2 (Send (_2, _4, _6)) )
# 738 "parser.ml"
               : 'stmt))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 6 : Ast.send_target) in
    let _4 = (Parsing.peek_val __caml_parser_env 4 : string) in
    let _6 = (Parsing.peek_val __caml_parser_env 2 : 'args) in
    Obj.repr(
# 97 "parser.mly"
                                                               ( mk_stmt1 2 (UnsafeSend (_2, _4, _6)) )
# 747 "parser.ml"
               : 'stmt))
; (fun __caml_parser_env ->
    let _3 = (Parsing.peek_val __caml_parser_env 2 : 'expr) in
    let _5 = (Parsing.peek_val __caml_parser_env 0 : 'stmt) in
    Obj.repr(
# 98 "parser.mly"
                               ( mk_stmt1 2 (If(_3, _5, mk_stmt1 5 (Seq([])))) )
# 755 "parser.ml"
               : 'stmt))
; (fun __caml_parser_env ->
    let _3 = (Parsing.peek_val __caml_parser_env 4 : 'expr) in
    let _5 = (Parsing.peek_val __caml_parser_env 2 : 'stmt) in
    let _7 = (Parsing.peek_val __caml_parser_env 0 : 'stmt) in
    Obj.repr(
# 99 "parser.mly"
                                         ( mk_stmt1 3 (If(_3, _5, _7)) )
# 764 "parser.ml"
               : 'stmt))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 2 : 'expr) in
    let _4 = (Parsing.peek_val __caml_parser_env 0 : 'stmt) in
    Obj.repr(
# 100 "parser.mly"
                       ( mk_stmt1 2 (While (_2, _4)) )
# 772 "parser.ml"
               : 'stmt))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 1 : 'stmt_list) in
    Obj.repr(
# 101 "parser.mly"
                            ( mk_stmt1 2 (Seq _2) )
# 779 "parser.ml"
               : 'stmt))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 3 : string) in
    let _4 = (Parsing.peek_val __caml_parser_env 1 : 'expr) in
    Obj.repr(
# 102 "parser.mly"
                                 ( mk_stmt1 2 (VarDecl(_2, _4)) )
# 787 "parser.ml"
               : 'stmt))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 7 : string) in
    let _5 = (Parsing.peek_val __caml_parser_env 4 : string) in
    let _7 = (Parsing.peek_val __caml_parser_env 2 : 'args) in
    Obj.repr(
# 103 "parser.mly"
                                                      ( mk_stmt1 2 (VarDecl(_2, mk_expr1 4 (New(_5,_7)))) )
# 796 "parser.ml"
               : 'stmt))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 4 : string) in
    let _3 = (Parsing.peek_val __caml_parser_env 2 : 'args) in
    Obj.repr(
# 104 "parser.mly"
                                    ( mk_stmt1 1 (CallStmt (_1, _3)) )
# 804 "parser.ml"
               : 'stmt))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 4 : string) in
    let _4 = (Parsing.peek_val __caml_parser_env 2 : 'args) in
    Obj.repr(
# 105 "parser.mly"
                                           ( mk_stmt1 2 (Become (_2, _4)) )
# 812 "parser.ml"
               : 'stmt))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 3 : string) in
    Obj.repr(
# 106 "parser.mly"
                                      ( mk_stmt1 2 (Become (_2, [])) )
# 819 "parser.ml"
               : 'stmt))
; (fun __caml_parser_env ->
    let _3 = (Parsing.peek_val __caml_parser_env 2 : 'select_cases) in
    let _4 = (Parsing.peek_val __caml_parser_env 1 : 'select_timeout_opt) in
    Obj.repr(
# 107 "parser.mly"
                                                         ( mk_stmt1 3 (Select(_3, _4)) )
# 827 "parser.ml"
               : 'stmt))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 1 : 'select_cases) in
    let _2 = (Parsing.peek_val __caml_parser_env 0 : 'select_case) in
    Obj.repr(
# 110 "parser.mly"
                             ( _1 @ [_2] )
# 835 "parser.ml"
               : 'select_cases))
; (fun __caml_parser_env ->
    Obj.repr(
# 111 "parser.mly"
                             ( [] )
# 841 "parser.ml"
               : 'select_cases))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 1 : 'select_cases) in
    let _2 = (Parsing.peek_val __caml_parser_env 0 : 'select_case) in
    Obj.repr(
# 114 "parser.mly"
                             ( _1 @ [_2] )
# 849 "parser.ml"
               : 'select_cases))
; (fun __caml_parser_env ->
    Obj.repr(
# 115 "parser.mly"
                             ( [] )
# 855 "parser.ml"
               : 'select_cases))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 4 : 'select_pat) in
    let _5 = (Parsing.peek_val __caml_parser_env 1 : 'stmts) in
    Obj.repr(
# 119 "parser.mly"
    ( { pat = _2; body = mk_stmt1 5 (Seq(_5)) } )
# 863 "parser.ml"
               : 'select_case))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 3 : string) in
    let _3 = (Parsing.peek_val __caml_parser_env 1 : 'opt_id_list) in
    Obj.repr(
# 123 "parser.mly"
    ( { meth = _1; vars = _3 } )
# 871 "parser.ml"
               : 'select_pat))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 0 : 'id_list) in
    Obj.repr(
# 126 "parser.mly"
            ( _1 )
# 878 "parser.ml"
               : 'opt_id_list))
; (fun __caml_parser_env ->
    Obj.repr(
# 127 "parser.mly"
                ( [] )
# 884 "parser.ml"
               : 'opt_id_list))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 0 : string) in
    Obj.repr(
# 130 "parser.mly"
                         ( [_1] )
# 891 "parser.ml"
               : 'id_list))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 2 : 'id_list) in
    let _3 = (Parsing.peek_val __caml_parser_env 0 : string) in
    Obj.repr(
# 131 "parser.mly"
                      ( _1 @ [_3] )
# 899 "parser.ml"
               : 'id_list))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 4 : int) in
    let _5 = (Parsing.peek_val __caml_parser_env 1 : 'stmts) in
    Obj.repr(
# 135 "parser.mly"
      ( (Some _2, Some (mk_stmt1 5 (Seq _5))) )
# 907 "parser.ml"
               : 'select_timeout_opt))
; (fun __caml_parser_env ->
    Obj.repr(
# 137 "parser.mly"
      ( (None, None) )
# 913 "parser.ml"
               : 'select_timeout_opt))
; (fun __caml_parser_env ->
    Obj.repr(
# 140 "parser.mly"
                 ( [] )
# 919 "parser.ml"
               : 'args))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 0 : 'arg_list) in
    Obj.repr(
# 141 "parser.mly"
                 ( _1 )
# 926 "parser.ml"
               : 'args))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 2 : string) in
    let _3 = (Parsing.peek_val __caml_parser_env 0 : 'expr) in
    Obj.repr(
# 144 "parser.mly"
                   ( [(mk_stmt1 1 (VarDecl(_1, _3)))] )
# 934 "parser.ml"
               : 'inits))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 4 : string) in
    let _3 = (Parsing.peek_val __caml_parser_env 2 : 'expr) in
    let _5 = (Parsing.peek_val __caml_parser_env 0 : 'inits) in
    Obj.repr(
# 145 "parser.mly"
                               ( (mk_stmt1 1 (VarDecl(_1, _3))) :: _5 )
# 943 "parser.ml"
               : 'inits))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 0 : float) in
    Obj.repr(
# 148 "parser.mly"
             ( mk_expr1 1 (Float _1) )
# 950 "parser.ml"
               : 'expr))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 0 : string) in
    Obj.repr(
# 149 "parser.mly"
              ( mk_expr1 1 (String _1) )
# 957 "parser.ml"
               : 'expr))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 0 : int) in
    Obj.repr(
# 150 "parser.mly"
           ( mk_expr1 1 (Int _1) )
# 964 "parser.ml"
               : 'expr))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 0 : string) in
    Obj.repr(
# 151 "parser.mly"
       ( mk_expr1 1 (Var _1) )
# 971 "parser.ml"
               : 'expr))
; (fun __caml_parser_env ->
    Obj.repr(
# 152 "parser.mly"
         ( mk_expr1 1 (Var "self") )
# 977 "parser.ml"
               : 'expr))
; (fun __caml_parser_env ->
    Obj.repr(
# 153 "parser.mly"
           ( mk_expr1 1 (Var "sender") )
# 983 "parser.ml"
               : 'expr))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 2 : 'expr) in
    let _3 = (Parsing.peek_val __caml_parser_env 0 : 'expr) in
    Obj.repr(
# 154 "parser.mly"
                   ( mk_expr1 2 (Binop ("+", _1, _3)) )
# 991 "parser.ml"
               : 'expr))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 2 : 'expr) in
    let _3 = (Parsing.peek_val __caml_parser_env 0 : 'expr) in
    Obj.repr(
# 155 "parser.mly"
                    ( mk_expr1 2 (Binop ("-", _1, _3)) )
# 999 "parser.ml"
               : 'expr))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 2 : 'expr) in
    let _3 = (Parsing.peek_val __caml_parser_env 0 : 'expr) in
    Obj.repr(
# 156 "parser.mly"
                    ( mk_expr1 2 (Binop ("*", _1, _3)) )
# 1007 "parser.ml"
               : 'expr))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 2 : 'expr) in
    let _3 = (Parsing.peek_val __caml_parser_env 0 : 'expr) in
    Obj.repr(
# 157 "parser.mly"
                  ( mk_expr1 2 (Binop ("/", _1, _3)) )
# 1015 "parser.ml"
               : 'expr))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 3 : string) in
    let _4 = (Parsing.peek_val __caml_parser_env 1 : 'args) in
    Obj.repr(
# 158 "parser.mly"
                              ( mk_expr1 1 (New (_2, _4)) )
# 1023 "parser.ml"
               : 'expr))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 3 : string) in
    let _3 = (Parsing.peek_val __caml_parser_env 1 : 'args) in
    Obj.repr(
# 159 "parser.mly"
                          ( mk_expr1 1 (Call (_1, _3)) )
# 1031 "parser.ml"
               : 'expr))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 2 : 'expr) in
    let _3 = (Parsing.peek_val __caml_parser_env 0 : 'expr) in
    Obj.repr(
# 160 "parser.mly"
                 ( mk_expr1 2 (Binop (">=", _1, _3)) )
# 1039 "parser.ml"
               : 'expr))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 2 : 'expr) in
    let _3 = (Parsing.peek_val __caml_parser_env 0 : 'expr) in
    Obj.repr(
# 161 "parser.mly"
                 ( mk_expr1 2 (Binop ("<=", _1, _3)) )
# 1047 "parser.ml"
               : 'expr))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 2 : 'expr) in
    let _3 = (Parsing.peek_val __caml_parser_env 0 : 'expr) in
    Obj.repr(
# 162 "parser.mly"
                 ( mk_expr1 2 (Binop (">", _1, _3)) )
# 1055 "parser.ml"
               : 'expr))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 2 : 'expr) in
    let _3 = (Parsing.peek_val __caml_parser_env 0 : 'expr) in
    Obj.repr(
# 163 "parser.mly"
                 ( mk_expr1 2 (Binop ("<", _1, _3)) )
# 1063 "parser.ml"
               : 'expr))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 2 : 'expr) in
    let _3 = (Parsing.peek_val __caml_parser_env 0 : 'expr) in
    Obj.repr(
# 164 "parser.mly"
                  ( mk_expr1 2 (Binop ("==", _1, _3)) )
# 1071 "parser.ml"
               : 'expr))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 2 : 'expr) in
    let _3 = (Parsing.peek_val __caml_parser_env 0 : 'expr) in
    Obj.repr(
# 165 "parser.mly"
                  ( mk_expr1 2 (Binop ("!=", _1, _3)) )
# 1079 "parser.ml"
               : 'expr))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 1 : 'expr) in
    Obj.repr(
# 166 "parser.mly"
                       ( _2 )
# 1086 "parser.ml"
               : 'expr))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 5 : Ast.send_target) in
    let _4 = (Parsing.peek_val __caml_parser_env 3 : string) in
    let _6 = (Parsing.peek_val __caml_parser_env 1 : 'args) in
    Obj.repr(
# 167 "parser.mly"
                                                  ( mk_expr1 1 (Now (_2, _4, _6)) )
# 1095 "parser.ml"
               : 'expr))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 5 : Ast.send_target) in
    let _4 = (Parsing.peek_val __caml_parser_env 3 : string) in
    let _6 = (Parsing.peek_val __caml_parser_env 1 : 'args) in
    Obj.repr(
# 168 "parser.mly"
                                                  ( mk_expr1 1 (Future (_2, _4, _6)) )
# 1104 "parser.ml"
               : 'expr))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 0 : 'expr) in
    Obj.repr(
# 169 "parser.mly"
                                                  ( mk_expr1 1 (Await _2) )
# 1111 "parser.ml"
               : 'expr))
(* Entry program *)
; (fun __caml_parser_env -> raise (Parsing.YYexit (Parsing.peek_val __caml_parser_env 0)))
|]
let yytables =
  { Parsing.actions=yyact;
    Parsing.transl_const=yytransl_const;
    Parsing.transl_block=yytransl_block;
    Parsing.lhs=yylhs;
    Parsing.len=yylen;
    Parsing.defred=yydefred;
    Parsing.dgoto=yydgoto;
    Parsing.sindex=yysindex;
    Parsing.rindex=yyrindex;
    Parsing.gindex=yygindex;
    Parsing.tablesize=yytablesize;
    Parsing.table=yytable;
    Parsing.check=yycheck;
    Parsing.error_function=parse_error;
    Parsing.names_const=yynames_const;
    Parsing.names_block=yynames_block }
let program (lexfun : Lexing.lexbuf -> token) (lexbuf : Lexing.lexbuf) =
   (Parsing.yyparse yytables 1 lexfun lexbuf : Ast.program)
