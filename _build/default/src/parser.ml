type token =
  | ID of (
# 13 "src/parser.mly"
        string
# 6 "src/parser.ml"
)
  | FLOATLIT of (
# 14 "src/parser.mly"
        float
# 11 "src/parser.ml"
)
  | INTLIT of (
# 15 "src/parser.mly"
        int
# 16 "src/parser.ml"
)
  | STRINGLIT of (
# 16 "src/parser.mly"
        string
# 21 "src/parser.ml"
)
  | METHOD
  | FLOAT
  | CALL
  | SEND
  | UNSAFESEND
  | REMOTE
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
# 2 "src/parser.mly"
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
# 77 "src/parser.ml"
let yytransl_const = [|
  261 (* METHOD *);
  262 (* FLOAT *);
  263 (* CALL *);
  264 (* SEND *);
  265 (* UNSAFESEND *);
  266 (* REMOTE *);
  267 (* IF *);
  268 (* THEN *);
  269 (* ELSE *);
  270 (* WHILE *);
  271 (* DO *);
  272 (* ASSIGN *);
  273 (* PLUS *);
  274 (* MINUS *);
  275 (* TIMES *);
  276 (* DIV *);
  277 (* LPAREN *);
  278 (* RPAREN *);
  279 (* LBRACE *);
  280 (* RBRACE *);
  281 (* SEMICOLON *);
  282 (* COMMA *);
  283 (* GE *);
  284 (* LE *);
  285 (* GT *);
  286 (* LT *);
  287 (* SELF *);
  288 (* SENDER *);
  289 (* CLASS *);
  290 (* SELECT *);
  291 (* CASE *);
  292 (* TIMEOUT *);
  293 (* ARROW *);
    0 (* EOF *);
  294 (* NEW *);
  295 (* VAR *);
  296 (* EQ *);
  297 (* NEQ *);
  298 (* DOT *);
  299 (* BECOME *);
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
\006\000\006\000\006\000\000\000"

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
\003\000\003\000\003\000\002\000"

let yydefred = "\000\000\
\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\
\084\000\000\000\000\000\002\000\000\000\026\000\000\000\000\000\
\000\000\000\000\000\000\001\000\000\000\006\000\000\000\065\000\
\067\000\066\000\000\000\069\000\070\000\000\000\000\000\000\000\
\000\000\000\000\000\000\000\000\000\000\000\000\005\000\000\000\
\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\
\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\
\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\
\000\000\000\000\000\000\083\000\000\000\000\000\000\000\000\000\
\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\
\015\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\
\010\000\017\000\021\000\000\000\011\000\076\000\000\000\000\000\
\000\000\000\000\000\000\000\000\000\000\009\000\000\000\075\000\
\027\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\
\013\000\014\000\000\000\000\000\018\000\019\000\000\000\025\000\
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
\009\000\016\000\010\000\011\000\031\000\032\000\061\000\062\000\
\033\000\063\000\064\000\109\000\133\000\134\000\145\000\162\000\
\177\000\178\000\192\000\216\000\217\000\000\000"

let yysindex = "\008\000\
\064\255\000\000\011\000\010\255\006\255\006\255\039\255\055\255\
\000\000\033\000\075\255\000\000\153\255\000\000\037\255\035\255\
\036\255\056\255\065\255\000\000\090\255\000\000\074\255\000\000\
\000\000\000\000\153\255\000\000\000\000\081\255\060\255\091\000\
\084\255\103\255\109\255\110\255\000\255\174\255\000\000\153\255\
\232\255\091\255\153\255\153\255\153\255\153\255\153\255\153\255\
\153\255\153\255\153\255\153\255\153\255\094\255\089\255\099\255\
\113\255\134\255\135\255\139\255\136\255\128\255\254\254\136\255\
\152\255\249\255\143\255\000\000\153\255\091\000\098\255\098\255\
\099\000\099\000\091\000\091\000\091\000\091\000\091\000\091\000\
\000\000\154\255\153\255\153\255\150\255\148\255\178\255\163\255\
\000\000\000\000\000\000\169\255\000\000\000\000\176\255\182\255\
\185\255\186\255\200\255\153\255\153\255\000\000\153\255\000\000\
\000\000\184\255\188\255\189\255\192\255\010\000\027\000\202\255\
\000\000\000\000\200\255\199\255\000\000\000\000\208\255\000\000\
\046\255\000\000\248\254\224\255\061\255\006\255\218\255\153\255\
\046\255\215\255\239\255\242\255\229\255\046\255\153\255\153\255\
\227\255\213\255\214\255\221\255\222\255\153\255\217\255\046\255\
\246\255\000\000\255\255\244\255\000\000\000\000\044\000\253\255\
\129\255\023\000\024\000\025\000\030\000\059\000\046\255\000\000\
\000\000\032\255\179\255\141\255\000\000\007\000\016\000\014\000\
\022\000\028\000\032\000\037\000\046\255\000\000\041\000\045\000\
\035\000\000\000\064\000\076\000\050\000\038\000\000\000\000\000\
\055\000\153\255\153\255\153\255\153\255\053\000\049\000\046\000\
\054\000\000\000\061\000\000\000\000\000\065\000\000\000\070\000\
\075\000\080\000\085\000\046\255\097\000\107\000\110\000\153\255\
\000\000\109\000\112\000\113\000\117\000\000\000\000\000\125\000\
\123\000\046\255\046\255\128\000\000\000\000\000\000\000\000\000\
\000\000\153\000\147\000\155\000\143\000\000\000\000\000\000\000\
\000\000"

let yyrindex = "\000\000\
\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\
\000\000\000\000\181\001\000\000\160\000\000\000\000\000\000\000\
\000\000\000\000\000\000\000\000\185\001\000\000\201\255\000\000\
\000\000\000\000\000\000\000\000\000\000\000\000\164\000\244\254\
\000\000\000\000\000\000\000\000\000\000\000\000\000\000\160\000\
\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\
\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\
\000\000\000\000\000\000\000\000\000\000\000\000\182\000\165\000\
\000\000\000\000\000\000\000\000\160\000\026\255\171\255\144\000\
\126\000\138\000\079\255\144\255\177\255\150\000\152\000\158\000\
\000\000\000\000\160\000\160\000\000\000\000\000\000\000\000\000\
\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\
\000\000\000\000\166\000\000\000\000\000\000\000\160\000\000\000\
\000\000\000\000\000\000\168\000\000\000\000\000\000\000\000\000\
\000\000\000\000\166\000\000\000\000\000\000\000\095\000\000\000\
\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\
\167\000\000\000\000\000\000\000\000\000\169\000\000\000\160\000\
\000\000\000\000\000\000\000\000\000\000\000\000\000\000\167\000\
\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\
\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\
\000\000\170\000\000\000\000\000\000\000\000\000\000\000\000\000\
\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\
\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\
\000\000\160\000\160\000\160\000\160\000\027\255\000\000\000\000\
\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\
\000\000\000\000\000\000\000\000\173\000\000\000\000\000\160\000\
\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\
\174\000\000\000\000\000\000\000\000\000\000\000\000\000\000\000\
\000\000\000\000\000\000\000\000\095\000\000\000\000\000\000\000\
\000\000"

let yygindex = "\000\000\
\000\000\252\255\021\000\000\000\000\000\230\255\129\001\241\255\
\216\255\000\000\000\000\082\001\125\255\142\255\054\001\000\000\
\000\000\000\000\000\000\000\000\000\000\000\000"

let yytablesize = 454
let yytable = "\067\000\
\041\000\017\000\150\000\059\000\058\000\059\000\014\000\135\000\
\001\000\007\000\012\000\066\000\136\000\007\000\144\000\015\000\
\070\000\071\000\072\000\073\000\074\000\075\000\076\000\077\000\
\078\000\079\000\080\000\039\000\095\000\144\000\013\000\022\000\
\020\000\039\000\039\000\039\000\060\000\039\000\060\000\018\000\
\039\000\039\000\097\000\098\000\174\000\088\000\123\000\008\000\
\091\000\039\000\039\000\008\000\124\000\125\000\126\000\019\000\
\127\000\034\000\190\000\128\000\039\000\014\000\112\000\003\000\
\004\000\039\000\175\000\176\000\129\000\039\000\015\000\005\000\
\006\000\110\000\111\000\004\000\035\000\036\000\037\000\130\000\
\038\000\042\000\005\000\006\000\131\000\043\000\227\000\228\000\
\132\000\214\000\004\000\138\000\139\000\077\000\040\000\152\000\
\007\000\005\000\006\000\021\000\077\000\143\000\008\000\077\000\
\077\000\054\000\055\000\007\000\151\000\056\000\057\000\069\000\
\168\000\008\000\082\000\158\000\046\000\047\000\081\000\083\000\
\140\000\141\000\007\000\182\000\048\000\049\000\050\000\051\000\
\008\000\023\000\024\000\025\000\026\000\084\000\085\000\086\000\
\180\000\052\000\053\000\087\000\058\000\023\000\024\000\025\000\
\026\000\200\000\201\000\202\000\203\000\027\000\167\000\089\000\
\092\000\023\000\024\000\025\000\026\000\096\000\078\000\028\000\
\029\000\027\000\181\000\100\000\094\000\078\000\030\000\220\000\
\078\000\078\000\099\000\028\000\029\000\027\000\023\000\024\000\
\025\000\026\000\030\000\023\000\024\000\025\000\026\000\028\000\
\029\000\071\000\102\000\071\000\071\000\103\000\030\000\079\000\
\071\000\101\000\027\000\071\000\071\000\104\000\079\000\027\000\
\108\000\079\000\079\000\105\000\028\000\029\000\106\000\107\000\
\113\000\028\000\029\000\065\000\114\000\116\000\115\000\068\000\
\179\000\068\000\068\000\068\000\068\000\121\000\068\000\119\000\
\137\000\068\000\068\000\068\000\068\000\068\000\068\000\159\000\
\122\000\044\000\045\000\046\000\047\000\146\000\142\000\147\000\
\068\000\068\000\148\000\048\000\049\000\050\000\051\000\153\000\
\044\000\045\000\046\000\047\000\149\000\068\000\154\000\155\000\
\052\000\053\000\048\000\049\000\050\000\051\000\156\000\157\000\
\164\000\044\000\045\000\046\000\047\000\161\000\163\000\052\000\
\053\000\093\000\166\000\048\000\049\000\050\000\051\000\169\000\
\170\000\171\000\044\000\045\000\046\000\047\000\172\000\183\000\
\052\000\053\000\117\000\185\000\048\000\049\000\050\000\051\000\
\184\000\191\000\186\000\044\000\045\000\046\000\047\000\193\000\
\187\000\052\000\053\000\118\000\188\000\048\000\049\000\050\000\
\051\000\189\000\194\000\198\000\044\000\045\000\046\000\047\000\
\195\000\204\000\052\000\053\000\165\000\205\000\048\000\049\000\
\050\000\051\000\197\000\044\000\045\000\046\000\047\000\199\000\
\173\000\208\000\206\000\052\000\053\000\048\000\049\000\050\000\
\051\000\209\000\207\000\210\000\044\000\045\000\046\000\047\000\
\211\000\215\000\052\000\053\000\196\000\212\000\048\000\049\000\
\050\000\051\000\213\000\044\000\045\000\046\000\047\000\075\000\
\075\000\075\000\075\000\052\000\053\000\048\000\049\000\050\000\
\051\000\075\000\075\000\075\000\075\000\048\000\049\000\050\000\
\051\000\218\000\052\000\053\000\219\000\221\000\075\000\075\000\
\222\000\223\000\052\000\053\000\073\000\224\000\073\000\073\000\
\073\000\073\000\225\000\073\000\226\000\229\000\073\000\073\000\
\074\000\230\000\074\000\074\000\074\000\074\000\072\000\074\000\
\072\000\072\000\074\000\074\000\080\000\072\000\081\000\233\000\
\072\000\072\000\231\000\080\000\082\000\081\000\080\000\080\000\
\081\000\081\000\232\000\082\000\003\000\061\000\082\000\082\000\
\004\000\062\000\016\000\023\000\020\000\024\000\031\000\090\000\
\028\000\060\000\056\000\055\000\120\000\160\000"

let yycheck = "\040\000\
\027\000\006\000\134\000\006\001\005\001\006\001\001\001\016\001\
\001\000\022\001\000\000\038\000\021\001\026\001\129\000\010\001\
\043\000\044\000\045\000\046\000\047\000\048\000\049\000\050\000\
\051\000\052\000\053\000\001\001\069\000\144\000\021\001\011\000\
\000\000\007\001\008\001\009\001\039\001\011\001\039\001\001\001\
\014\001\021\000\083\000\084\000\159\000\061\000\001\001\022\001\
\064\000\023\001\024\001\026\001\007\001\008\001\009\001\001\001\
\011\001\021\001\173\000\014\001\034\001\001\001\103\000\000\001\
\001\001\039\001\035\001\036\001\023\001\043\001\010\001\008\001\
\009\001\100\000\101\000\001\001\042\001\042\001\023\001\034\001\
\016\001\001\001\008\001\009\001\039\001\026\001\218\000\219\000\
\043\001\204\000\001\001\031\001\032\001\015\001\021\001\136\000\
\033\001\008\001\009\001\025\001\022\001\128\000\039\001\025\001\
\026\001\022\001\004\001\033\001\135\000\001\001\001\001\021\001\
\153\000\039\001\026\001\142\000\019\001\020\001\025\001\021\001\
\125\000\126\000\033\001\164\000\027\001\028\001\029\001\030\001\
\039\001\001\001\002\001\003\001\004\001\021\001\001\001\001\001\
\163\000\040\001\041\001\001\001\005\001\001\001\002\001\003\001\
\004\001\186\000\187\000\188\000\189\000\021\001\022\001\024\001\
\001\001\001\001\002\001\003\001\004\001\004\001\015\001\031\001\
\032\001\021\001\022\001\016\001\022\001\022\001\038\001\208\000\
\025\001\026\001\021\001\031\001\032\001\021\001\001\001\002\001\
\003\001\004\001\038\001\001\001\002\001\003\001\004\001\031\001\
\032\001\015\001\024\001\017\001\018\001\021\001\038\001\015\001\
\022\001\016\001\021\001\025\001\026\001\022\001\022\001\021\001\
\001\001\025\001\026\001\022\001\031\001\032\001\022\001\022\001\
\025\001\031\001\032\001\038\001\025\001\022\001\026\001\015\001\
\038\001\017\001\018\001\019\001\020\001\023\001\022\001\022\001\
\001\001\025\001\026\001\027\001\028\001\029\001\030\001\015\001\
\025\001\017\001\018\001\019\001\020\001\023\001\021\001\001\001\
\040\001\041\001\001\001\027\001\028\001\029\001\030\001\021\001\
\017\001\018\001\019\001\020\001\024\001\022\001\042\001\042\001\
\040\001\041\001\027\001\028\001\029\001\030\001\042\001\042\001\
\021\001\017\001\018\001\019\001\020\001\024\001\016\001\040\001\
\041\001\025\001\022\001\027\001\028\001\029\001\030\001\001\001\
\001\001\001\001\017\001\018\001\019\001\020\001\001\001\025\001\
\040\001\041\001\025\001\022\001\027\001\028\001\029\001\030\001\
\025\001\001\001\021\001\017\001\018\001\019\001\020\001\003\001\
\021\001\040\001\041\001\025\001\021\001\027\001\028\001\029\001\
\030\001\021\001\024\001\022\001\017\001\018\001\019\001\020\001\
\001\001\013\001\040\001\041\001\025\001\021\001\027\001\028\001\
\029\001\030\001\025\001\017\001\018\001\019\001\020\001\025\001\
\022\001\021\001\037\001\040\001\041\001\027\001\028\001\029\001\
\030\001\025\001\037\001\022\001\017\001\018\001\019\001\020\001\
\022\001\001\001\040\001\041\001\025\001\022\001\027\001\028\001\
\029\001\030\001\022\001\017\001\018\001\019\001\020\001\017\001\
\018\001\019\001\020\001\040\001\041\001\027\001\028\001\029\001\
\030\001\027\001\028\001\029\001\030\001\027\001\028\001\029\001\
\030\001\023\001\040\001\041\001\023\001\025\001\040\001\041\001\
\025\001\025\001\040\001\041\001\015\001\025\001\017\001\018\001\
\019\001\020\001\022\001\022\001\026\001\022\001\025\001\026\001\
\015\001\001\001\017\001\018\001\019\001\020\001\015\001\022\001\
\017\001\018\001\025\001\026\001\015\001\022\001\015\001\025\001\
\025\001\026\001\024\001\022\001\015\001\022\001\025\001\026\001\
\025\001\026\001\024\001\022\001\000\000\022\001\025\001\026\001\
\000\000\022\001\005\001\022\001\024\001\022\001\024\001\063\000\
\024\001\024\001\022\001\022\001\115\000\144\000"

let yynames_const = "\
  METHOD\000\
  FLOAT\000\
  CALL\000\
  SEND\000\
  UNSAFESEND\000\
  REMOTE\000\
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
# 33 "src/parser.mly"
              ( _1 )
# 436 "src/parser.ml"
               : Ast.program))
; (fun __caml_parser_env ->
    Obj.repr(
# 34 "src/parser.mly"
              ( raise (Syntax_error (loc_of_rhs 1, "syntax error in program")) )
# 442 "src/parser.ml"
               : Ast.program))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 0 : 'decl) in
    Obj.repr(
# 37 "src/parser.mly"
         ( [_1] )
# 449 "src/parser.ml"
               : 'decls))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 1 : 'decl) in
    Obj.repr(
# 38 "src/parser.mly"
                   ( [_1] )
# 456 "src/parser.ml"
               : 'decls))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 2 : 'decl) in
    let _3 = (Parsing.peek_val __caml_parser_env 0 : 'decls) in
    Obj.repr(
# 39 "src/parser.mly"
                         ( _1 :: _3 )
# 464 "src/parser.ml"
               : 'decls))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 1 : 'decl) in
    let _2 = (Parsing.peek_val __caml_parser_env 0 : 'decls) in
    Obj.repr(
# 40 "src/parser.mly"
               ( _1 :: _2 )
# 472 "src/parser.ml"
               : 'decls))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 0 : 'expr) in
    Obj.repr(
# 43 "src/parser.mly"
                             ( [_1] )
# 479 "src/parser.ml"
               : 'arg_list))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 2 : 'arg_list) in
    let _3 = (Parsing.peek_val __caml_parser_env 0 : 'expr) in
    Obj.repr(
# 44 "src/parser.mly"
                               ( _1 @ [_3] )
# 487 "src/parser.ml"
               : 'arg_list))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 4 : string) in
    let _4 = (Parsing.peek_val __caml_parser_env 2 : 'fields) in
    let _5 = (Parsing.peek_val __caml_parser_env 1 : 'methods) in
    Obj.repr(
# 47 "src/parser.mly"
                                           ( Class { cname = _2; fields = _4; methods = _5 } )
# 496 "src/parser.ml"
               : 'decl))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 3 : string) in
    let _4 = (Parsing.peek_val __caml_parser_env 1 : 'methods) in
    Obj.repr(
# 48 "src/parser.mly"
                                           ( Class { cname = _2; fields = []; methods = _4 } )
# 504 "src/parser.ml"
               : 'decl))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 3 : string) in
    let _4 = (Parsing.peek_val __caml_parser_env 1 : 'expr) in
    Obj.repr(
# 49 "src/parser.mly"
                                           ( Global (mk_stmt1 2 (VarDecl (_2, _4))) )
# 512 "src/parser.ml"
               : 'decl))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 7 : string) in
    let _5 = (Parsing.peek_val __caml_parser_env 4 : string) in
    let _7 = (Parsing.peek_val __caml_parser_env 2 : 'args) in
    Obj.repr(
# 51 "src/parser.mly"
    ( Global (mk_stmt1 2 (VarDecl (_2, mk_expr1 4 (New (_5, _7))))) )
# 521 "src/parser.ml"
               : 'decl))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 6 : Ast.send_target) in
    let _4 = (Parsing.peek_val __caml_parser_env 4 : string) in
    let _6 = (Parsing.peek_val __caml_parser_env 2 : 'args) in
    Obj.repr(
# 52 "src/parser.mly"
                                                                       ( Global (mk_stmt1 1 (Send (_2, _4, _6))) )
# 530 "src/parser.ml"
               : 'decl))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 6 : Ast.send_target) in
    let _4 = (Parsing.peek_val __caml_parser_env 4 : string) in
    let _6 = (Parsing.peek_val __caml_parser_env 2 : 'args) in
    Obj.repr(
# 53 "src/parser.mly"
                                                                       ( Global (mk_stmt1 1 (UnsafeSend (_2, _4, _6))) )
# 539 "src/parser.ml"
               : 'decl))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 4 : string) in
    let _3 = (Parsing.peek_val __caml_parser_env 2 : 'args) in
    Obj.repr(
# 54 "src/parser.mly"
                                           ( Global (mk_stmt1 1 (CallStmt (_1, _3))) )
# 547 "src/parser.ml"
               : 'decl))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 0 : 'field) in
    Obj.repr(
# 57 "src/parser.mly"
          ( [_1] )
# 554 "src/parser.ml"
               : 'fields))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 1 : 'field) in
    let _2 = (Parsing.peek_val __caml_parser_env 0 : 'fields) in
    Obj.repr(
# 58 "src/parser.mly"
                 ( _1 :: _2 )
# 562 "src/parser.ml"
               : 'fields))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 3 : string) in
    let _4 = (Parsing.peek_val __caml_parser_env 1 : 'expr) in
    Obj.repr(
# 61 "src/parser.mly"
                                   ( mk_stmt1 2  (VarDecl (_2, _4)) )
# 570 "src/parser.ml"
               : 'field))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 3 : string) in
    let _4 = (Parsing.peek_val __caml_parser_env 1 : 'expr) in
    Obj.repr(
# 62 "src/parser.mly"
                                 ( mk_stmt1 2 (VarDecl (_2, _4)) )
# 578 "src/parser.ml"
               : 'field))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 0 : 'method_decl) in
    Obj.repr(
# 65 "src/parser.mly"
                ( [_1] )
# 585 "src/parser.ml"
               : 'methods))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 1 : 'method_decl) in
    let _2 = (Parsing.peek_val __caml_parser_env 0 : 'methods) in
    Obj.repr(
# 66 "src/parser.mly"
                        ( _1 :: _2 )
# 593 "src/parser.ml"
               : 'methods))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 6 : string) in
    let _4 = (Parsing.peek_val __caml_parser_env 4 : 'param_list) in
    let _7 = (Parsing.peek_val __caml_parser_env 1 : 'stmts) in
    Obj.repr(
# 70 "src/parser.mly"
    ( { mname = _2; params = _4; body = mk_stmt1 2 (Seq _7) } )
# 602 "src/parser.ml"
               : 'method_decl))
; (fun __caml_parser_env ->
    Obj.repr(
# 73 "src/parser.mly"
       ( [] )
# 608 "src/parser.ml"
               : 'param_list))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 0 : string) in
    Obj.repr(
# 74 "src/parser.mly"
       ( [_1] )
# 615 "src/parser.ml"
               : 'param_list))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 2 : string) in
    let _3 = (Parsing.peek_val __caml_parser_env 0 : 'param_list) in
    Obj.repr(
# 75 "src/parser.mly"
                        ( _1::_3 )
# 623 "src/parser.ml"
               : 'param_list))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 0 : string) in
    Obj.repr(
# 78 "src/parser.mly"
                                                      ( LocalTarget _1 )
# 630 "src/parser.ml"
               : Ast.send_target))
; (fun __caml_parser_env ->
    let _3 = (Parsing.peek_val __caml_parser_env 3 : string) in
    let _5 = (Parsing.peek_val __caml_parser_env 1 : string) in
    Obj.repr(
# 79 "src/parser.mly"
                                                      ( RemoteTarget (_3, _5) )
# 638 "src/parser.ml"
               : Ast.send_target))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 0 : 'stmt) in
    Obj.repr(
# 82 "src/parser.mly"
         ( [_1] )
# 645 "src/parser.ml"
               : 'stmts))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 1 : 'stmt) in
    let _2 = (Parsing.peek_val __caml_parser_env 0 : 'stmts) in
    Obj.repr(
# 83 "src/parser.mly"
               ( _1 :: _2 )
# 653 "src/parser.ml"
               : 'stmts))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 1 : 'stmt) in
    let _2 = (Parsing.peek_val __caml_parser_env 0 : 'stmt_list) in
    Obj.repr(
# 86 "src/parser.mly"
                   ( _1::_2 )
# 661 "src/parser.ml"
               : 'stmt_list))
; (fun __caml_parser_env ->
    Obj.repr(
# 87 "src/parser.mly"
                   ( [] )
# 667 "src/parser.ml"
               : 'stmt_list))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 3 : string) in
    let _3 = (Parsing.peek_val __caml_parser_env 1 : 'expr) in
    Obj.repr(
# 90 "src/parser.mly"
                             ( mk_stmt1 1 (Assign (_1, _3)) )
# 675 "src/parser.ml"
               : 'stmt))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 4 : string) in
    let _4 = (Parsing.peek_val __caml_parser_env 2 : 'args) in
    Obj.repr(
# 91 "src/parser.mly"
                                         ( mk_stmt1 2 (CallStmt (_2, _4)) )
# 683 "src/parser.ml"
               : 'stmt))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 3 : string) in
    Obj.repr(
# 92 "src/parser.mly"
                                    ( mk_stmt1 2 (CallStmt (_2, [])) )
# 690 "src/parser.ml"
               : 'stmt))
; (fun __caml_parser_env ->
    let _4 = (Parsing.peek_val __caml_parser_env 4 : string) in
    let _6 = (Parsing.peek_val __caml_parser_env 2 : 'args) in
    Obj.repr(
# 93 "src/parser.mly"
                                                  ( mk_stmt1 4 (Send(LocalTarget "self", _4, _6)) )
# 698 "src/parser.ml"
               : 'stmt))
; (fun __caml_parser_env ->
    let _4 = (Parsing.peek_val __caml_parser_env 4 : string) in
    let _6 = (Parsing.peek_val __caml_parser_env 2 : 'args) in
    Obj.repr(
# 94 "src/parser.mly"
                                                    ( mk_stmt1 4 (Send (LocalTarget "sender", _4, _6)) )
# 706 "src/parser.ml"
               : 'stmt))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 6 : Ast.send_target) in
    let _4 = (Parsing.peek_val __caml_parser_env 4 : string) in
    let _6 = (Parsing.peek_val __caml_parser_env 2 : 'args) in
    Obj.repr(
# 95 "src/parser.mly"
                                                         ( mk_stmt1 2 (Send (_2, _4, _6)) )
# 715 "src/parser.ml"
               : 'stmt))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 6 : Ast.send_target) in
    let _4 = (Parsing.peek_val __caml_parser_env 4 : string) in
    let _6 = (Parsing.peek_val __caml_parser_env 2 : 'args) in
    Obj.repr(
# 96 "src/parser.mly"
                                                               ( mk_stmt1 2 (UnsafeSend (_2, _4, _6)) )
# 724 "src/parser.ml"
               : 'stmt))
; (fun __caml_parser_env ->
    let _3 = (Parsing.peek_val __caml_parser_env 2 : 'expr) in
    let _5 = (Parsing.peek_val __caml_parser_env 0 : 'stmt) in
    Obj.repr(
# 97 "src/parser.mly"
                               ( mk_stmt1 2 (If(_3, _5, mk_stmt1 5 (Seq([])))) )
# 732 "src/parser.ml"
               : 'stmt))
; (fun __caml_parser_env ->
    let _3 = (Parsing.peek_val __caml_parser_env 4 : 'expr) in
    let _5 = (Parsing.peek_val __caml_parser_env 2 : 'stmt) in
    let _7 = (Parsing.peek_val __caml_parser_env 0 : 'stmt) in
    Obj.repr(
# 98 "src/parser.mly"
                                         ( mk_stmt1 3 (If(_3, _5, _7)) )
# 741 "src/parser.ml"
               : 'stmt))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 2 : 'expr) in
    let _4 = (Parsing.peek_val __caml_parser_env 0 : 'stmt) in
    Obj.repr(
# 99 "src/parser.mly"
                       ( mk_stmt1 2 (While (_2, _4)) )
# 749 "src/parser.ml"
               : 'stmt))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 1 : 'stmt_list) in
    Obj.repr(
# 100 "src/parser.mly"
                            ( mk_stmt1 2 (Seq _2) )
# 756 "src/parser.ml"
               : 'stmt))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 3 : string) in
    let _4 = (Parsing.peek_val __caml_parser_env 1 : 'expr) in
    Obj.repr(
# 101 "src/parser.mly"
                                 ( mk_stmt1 2 (VarDecl(_2, _4)) )
# 764 "src/parser.ml"
               : 'stmt))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 7 : string) in
    let _5 = (Parsing.peek_val __caml_parser_env 4 : string) in
    let _7 = (Parsing.peek_val __caml_parser_env 2 : 'args) in
    Obj.repr(
# 102 "src/parser.mly"
                                                      ( mk_stmt1 2 (VarDecl(_2, mk_expr1 4 (New(_5,_7)))) )
# 773 "src/parser.ml"
               : 'stmt))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 4 : string) in
    let _3 = (Parsing.peek_val __caml_parser_env 2 : 'args) in
    Obj.repr(
# 103 "src/parser.mly"
                                    ( mk_stmt1 1 (CallStmt (_1, _3)) )
# 781 "src/parser.ml"
               : 'stmt))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 4 : string) in
    let _4 = (Parsing.peek_val __caml_parser_env 2 : 'args) in
    Obj.repr(
# 104 "src/parser.mly"
                                           ( mk_stmt1 2 (Become (_2, _4)) )
# 789 "src/parser.ml"
               : 'stmt))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 3 : string) in
    Obj.repr(
# 105 "src/parser.mly"
                                      ( mk_stmt1 2 (Become (_2, [])) )
# 796 "src/parser.ml"
               : 'stmt))
; (fun __caml_parser_env ->
    let _3 = (Parsing.peek_val __caml_parser_env 2 : 'select_cases) in
    let _4 = (Parsing.peek_val __caml_parser_env 1 : 'select_timeout_opt) in
    Obj.repr(
# 106 "src/parser.mly"
                                                         ( mk_stmt1 3 (Select(_3, _4)) )
# 804 "src/parser.ml"
               : 'stmt))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 1 : 'select_cases) in
    let _2 = (Parsing.peek_val __caml_parser_env 0 : 'select_case) in
    Obj.repr(
# 109 "src/parser.mly"
                             ( _1 @ [_2] )
# 812 "src/parser.ml"
               : 'select_cases))
; (fun __caml_parser_env ->
    Obj.repr(
# 110 "src/parser.mly"
                             ( [] )
# 818 "src/parser.ml"
               : 'select_cases))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 1 : 'select_cases) in
    let _2 = (Parsing.peek_val __caml_parser_env 0 : 'select_case) in
    Obj.repr(
# 113 "src/parser.mly"
                             ( _1 @ [_2] )
# 826 "src/parser.ml"
               : 'select_cases))
; (fun __caml_parser_env ->
    Obj.repr(
# 114 "src/parser.mly"
                             ( [] )
# 832 "src/parser.ml"
               : 'select_cases))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 4 : 'select_pat) in
    let _5 = (Parsing.peek_val __caml_parser_env 1 : 'stmts) in
    Obj.repr(
# 118 "src/parser.mly"
    ( { pat = _2; body = mk_stmt1 5 (Seq(_5)) } )
# 840 "src/parser.ml"
               : 'select_case))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 3 : string) in
    let _3 = (Parsing.peek_val __caml_parser_env 1 : 'opt_id_list) in
    Obj.repr(
# 122 "src/parser.mly"
    ( { meth = _1; vars = _3 } )
# 848 "src/parser.ml"
               : 'select_pat))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 0 : 'id_list) in
    Obj.repr(
# 125 "src/parser.mly"
            ( _1 )
# 855 "src/parser.ml"
               : 'opt_id_list))
; (fun __caml_parser_env ->
    Obj.repr(
# 126 "src/parser.mly"
                ( [] )
# 861 "src/parser.ml"
               : 'opt_id_list))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 0 : string) in
    Obj.repr(
# 129 "src/parser.mly"
                         ( [_1] )
# 868 "src/parser.ml"
               : 'id_list))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 2 : 'id_list) in
    let _3 = (Parsing.peek_val __caml_parser_env 0 : string) in
    Obj.repr(
# 130 "src/parser.mly"
                      ( _1 @ [_3] )
# 876 "src/parser.ml"
               : 'id_list))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 4 : int) in
    let _5 = (Parsing.peek_val __caml_parser_env 1 : 'stmts) in
    Obj.repr(
# 134 "src/parser.mly"
      ( (Some _2, Some (mk_stmt1 5 (Seq _5))) )
# 884 "src/parser.ml"
               : 'select_timeout_opt))
; (fun __caml_parser_env ->
    Obj.repr(
# 136 "src/parser.mly"
      ( (None, None) )
# 890 "src/parser.ml"
               : 'select_timeout_opt))
; (fun __caml_parser_env ->
    Obj.repr(
# 139 "src/parser.mly"
                 ( [] )
# 896 "src/parser.ml"
               : 'args))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 0 : 'arg_list) in
    Obj.repr(
# 140 "src/parser.mly"
                 ( _1 )
# 903 "src/parser.ml"
               : 'args))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 2 : string) in
    let _3 = (Parsing.peek_val __caml_parser_env 0 : 'expr) in
    Obj.repr(
# 143 "src/parser.mly"
                   ( [(mk_stmt1 1 (VarDecl(_1, _3)))] )
# 911 "src/parser.ml"
               : 'inits))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 4 : string) in
    let _3 = (Parsing.peek_val __caml_parser_env 2 : 'expr) in
    let _5 = (Parsing.peek_val __caml_parser_env 0 : 'inits) in
    Obj.repr(
# 144 "src/parser.mly"
                               ( (mk_stmt1 1 (VarDecl(_1, _3))) :: _5 )
# 920 "src/parser.ml"
               : 'inits))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 0 : float) in
    Obj.repr(
# 147 "src/parser.mly"
             ( mk_expr1 1 (Float _1) )
# 927 "src/parser.ml"
               : 'expr))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 0 : string) in
    Obj.repr(
# 148 "src/parser.mly"
              ( mk_expr1 1 (String _1) )
# 934 "src/parser.ml"
               : 'expr))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 0 : int) in
    Obj.repr(
# 149 "src/parser.mly"
           ( mk_expr1 1 (Int _1) )
# 941 "src/parser.ml"
               : 'expr))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 0 : string) in
    Obj.repr(
# 150 "src/parser.mly"
       ( mk_expr1 1 (Var _1) )
# 948 "src/parser.ml"
               : 'expr))
; (fun __caml_parser_env ->
    Obj.repr(
# 151 "src/parser.mly"
         ( mk_expr1 1 (Var "self") )
# 954 "src/parser.ml"
               : 'expr))
; (fun __caml_parser_env ->
    Obj.repr(
# 152 "src/parser.mly"
           ( mk_expr1 1 (Var "sender") )
# 960 "src/parser.ml"
               : 'expr))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 2 : 'expr) in
    let _3 = (Parsing.peek_val __caml_parser_env 0 : 'expr) in
    Obj.repr(
# 153 "src/parser.mly"
                   ( mk_expr1 2 (Binop ("+", _1, _3)) )
# 968 "src/parser.ml"
               : 'expr))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 2 : 'expr) in
    let _3 = (Parsing.peek_val __caml_parser_env 0 : 'expr) in
    Obj.repr(
# 154 "src/parser.mly"
                    ( mk_expr1 2 (Binop ("-", _1, _3)) )
# 976 "src/parser.ml"
               : 'expr))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 2 : 'expr) in
    let _3 = (Parsing.peek_val __caml_parser_env 0 : 'expr) in
    Obj.repr(
# 155 "src/parser.mly"
                    ( mk_expr1 2 (Binop ("*", _1, _3)) )
# 984 "src/parser.ml"
               : 'expr))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 2 : 'expr) in
    let _3 = (Parsing.peek_val __caml_parser_env 0 : 'expr) in
    Obj.repr(
# 156 "src/parser.mly"
                  ( mk_expr1 2 (Binop ("/", _1, _3)) )
# 992 "src/parser.ml"
               : 'expr))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 3 : string) in
    let _4 = (Parsing.peek_val __caml_parser_env 1 : 'args) in
    Obj.repr(
# 157 "src/parser.mly"
                              ( mk_expr1 1 (New (_2, _4)) )
# 1000 "src/parser.ml"
               : 'expr))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 3 : string) in
    let _3 = (Parsing.peek_val __caml_parser_env 1 : 'args) in
    Obj.repr(
# 158 "src/parser.mly"
                          ( mk_expr1 1 (Call (_1, _3)) )
# 1008 "src/parser.ml"
               : 'expr))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 2 : 'expr) in
    let _3 = (Parsing.peek_val __caml_parser_env 0 : 'expr) in
    Obj.repr(
# 159 "src/parser.mly"
                 ( mk_expr1 2 (Binop (">=", _1, _3)) )
# 1016 "src/parser.ml"
               : 'expr))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 2 : 'expr) in
    let _3 = (Parsing.peek_val __caml_parser_env 0 : 'expr) in
    Obj.repr(
# 160 "src/parser.mly"
                 ( mk_expr1 2 (Binop ("<=", _1, _3)) )
# 1024 "src/parser.ml"
               : 'expr))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 2 : 'expr) in
    let _3 = (Parsing.peek_val __caml_parser_env 0 : 'expr) in
    Obj.repr(
# 161 "src/parser.mly"
                 ( mk_expr1 2 (Binop (">", _1, _3)) )
# 1032 "src/parser.ml"
               : 'expr))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 2 : 'expr) in
    let _3 = (Parsing.peek_val __caml_parser_env 0 : 'expr) in
    Obj.repr(
# 162 "src/parser.mly"
                 ( mk_expr1 2 (Binop ("<", _1, _3)) )
# 1040 "src/parser.ml"
               : 'expr))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 2 : 'expr) in
    let _3 = (Parsing.peek_val __caml_parser_env 0 : 'expr) in
    Obj.repr(
# 163 "src/parser.mly"
                  ( mk_expr1 2 (Binop ("==", _1, _3)) )
# 1048 "src/parser.ml"
               : 'expr))
; (fun __caml_parser_env ->
    let _1 = (Parsing.peek_val __caml_parser_env 2 : 'expr) in
    let _3 = (Parsing.peek_val __caml_parser_env 0 : 'expr) in
    Obj.repr(
# 164 "src/parser.mly"
                  ( mk_expr1 2 (Binop ("!=", _1, _3)) )
# 1056 "src/parser.ml"
               : 'expr))
; (fun __caml_parser_env ->
    let _2 = (Parsing.peek_val __caml_parser_env 1 : 'expr) in
    Obj.repr(
# 165 "src/parser.mly"
                       ( _2 )
# 1063 "src/parser.ml"
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
