type token =
  | ID of (
# 13 "src/parser.mly"
        string
# 6 "src/parser.mli"
)
  | FLOATLIT of (
# 14 "src/parser.mly"
        float
# 11 "src/parser.mli"
)
  | INTLIT of (
# 15 "src/parser.mly"
        int
# 16 "src/parser.mli"
)
  | STRINGLIT of (
# 16 "src/parser.mly"
        string
# 21 "src/parser.mli"
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

val program :
  (Lexing.lexbuf  -> token) -> Lexing.lexbuf -> Ast.program
