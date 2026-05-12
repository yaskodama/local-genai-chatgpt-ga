type token =
  | ID of (
# 13 "parser.mly"
        string
# 6 "parser.mli"
)
  | FLOATLIT of (
# 14 "parser.mly"
        float
# 11 "parser.mli"
)
  | INTLIT of (
# 15 "parser.mly"
        int
# 16 "parser.mli"
)
  | STRINGLIT of (
# 16 "parser.mly"
        string
# 21 "parser.mli"
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

val program :
  (Lexing.lexbuf  -> token) -> Lexing.lexbuf -> Ast.program
