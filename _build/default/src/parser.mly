%{
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
%}
%token <string> ID
%token <float> FLOATLIT
%token <int> INTLIT
%token <string> STRINGLIT
%token METHOD FLOAT CALL SEND UNSAFESEND REMOTE
%token IF THEN ELSE WHILE DO
%token ASSIGN PLUS MINUS TIMES DIV LPAREN RPAREN LBRACE RBRACE SEMICOLON COMMA
%token GE LE GT LT SELF SENDER CLASS
%token SELECT CASE TIMEOUT
%token ARROW /* -> */
%token EOF NEW
%token VAR EQ NEQ DOT BECOME
%left PLUS MINUS
%left TIMES DIV
%start program
%type <Ast.program> program
%type <Ast.send_target> send_target
%%

program:
  | decls EOF { $1 }
  | error EOF { raise (Syntax_error (loc_of_rhs 1, "syntax error in program")) }
  
decls:
  | decl { [$1] }
  | decl SEMICOLON { [$1] }
  | decl SEMICOLON decls { $1 :: $3 }
  | decl decls { $1 :: $2 }

arg_list:
  expr                       { [$1] }
  | arg_list COMMA expr        { $1 @ [$3] }

decl:
  | CLASS ID LBRACE fields methods RBRACE  { Class { cname = $2; fields = $4; methods = $5 } }
  | CLASS ID LBRACE methods RBRACE         { Class { cname = $2; fields = []; methods = $4 } }
  | VAR ID ASSIGN expr SEMICOLON           { Global (mk_stmt1 2 (VarDecl ($2, $4))) }
  | VAR ID ASSIGN NEW ID LPAREN args RPAREN SEMICOLON
    { Global (mk_stmt1 2 (VarDecl ($2, mk_expr1 4 (New ($5, $7))))) }
  | SEND send_target DOT ID LPAREN args RPAREN SEMICOLON               { Global (mk_stmt1 1 (Send ($2, $4, $6))) }
  | UNSAFESEND send_target DOT ID LPAREN args RPAREN SEMICOLON         { Global (mk_stmt1 1 (UnsafeSend ($2, $4, $6))) }
  | ID LPAREN args RPAREN SEMICOLON        { Global (mk_stmt1 1 (CallStmt ($1, $3))) }

fields:
  | field { [$1] }
  | field fields { $1 :: $2 }

field:
  | FLOAT ID ASSIGN expr SEMICOLON { mk_stmt1 2  (VarDecl ($2, $4)) }
  | VAR ID ASSIGN expr SEMICOLON { mk_stmt1 2 (VarDecl ($2, $4)) }
  
methods:
  | method_decl { [$1] }
  | method_decl methods { $1 :: $2 }

method_decl:
  | METHOD ID LPAREN param_list RPAREN LBRACE stmts RBRACE
    { { mname = $2; params = $4; body = mk_stmt1 2 (Seq $7) } }

param_list:
  |    { [] }
  | ID { [$1] }
  | ID COMMA param_list { $1::$3 }

send_target:
    ID                                                { LocalTarget $1 }
  | REMOTE LPAREN STRINGLIT COMMA STRINGLIT RPAREN    { RemoteTarget ($3, $5) }

stmts:
  | stmt { [$1] }
  | stmt stmts { $1 :: $2 }

stmt_list:
  | stmt stmt_list { $1::$2 }
  |                { [] }
  
stmt:
  | ID ASSIGN expr SEMICOLON { mk_stmt1 1 (Assign ($1, $3)) }
  | CALL ID LPAREN args RPAREN SEMICOLON { mk_stmt1 2 (CallStmt ($2, $4)) }
  | CALL ID LPAREN RPAREN SEMICOLON { mk_stmt1 2 (CallStmt ($2, [])) }
  | SEND SELF DOT ID LPAREN args RPAREN SEMICOLON { mk_stmt1 4 (Send(LocalTarget "self", $4, $6)) }
  | SEND SENDER DOT ID LPAREN args RPAREN SEMICOLON { mk_stmt1 4 (Send (LocalTarget "sender", $4, $6)) }
  | SEND send_target DOT ID LPAREN args RPAREN SEMICOLON { mk_stmt1 2 (Send ($2, $4, $6)) }
  | UNSAFESEND send_target DOT ID LPAREN args RPAREN SEMICOLON { mk_stmt1 2 (UnsafeSend ($2, $4, $6)) }
  | IF LPAREN expr RPAREN stmt { mk_stmt1 2 (If($3, $5, mk_stmt1 5 (Seq([])))) }
  | IF LPAREN expr RPAREN stmt ELSE stmt { mk_stmt1 3 (If($3, $5, $7)) }
  | WHILE expr DO stmt { mk_stmt1 2 (While ($2, $4)) }
  | LBRACE stmt_list RBRACE { mk_stmt1 2 (Seq $2) }
  | VAR ID ASSIGN expr SEMICOLON { mk_stmt1 2 (VarDecl($2, $4)) }
  | VAR ID ASSIGN NEW ID LPAREN args RPAREN SEMICOLON { mk_stmt1 2 (VarDecl($2, mk_expr1 4 (New($5,$7)))) }
  | ID LPAREN args RPAREN SEMICOLON { mk_stmt1 1 (CallStmt ($1, $3)) }
  | BECOME ID LPAREN args RPAREN SEMICOLON { mk_stmt1 2 (Become ($2, $4)) } 
  | BECOME ID LPAREN RPAREN SEMICOLON { mk_stmt1 2 (Become ($2, [])) }
  | SELECT LBRACE select_cases select_timeout_opt RBRACE { mk_stmt1 3 (Select($3, $4)) }

select_cases:
    select_cases select_case { $1 @ [$2] }
  | /* empty */              { [] }

select_cases:
    select_cases select_case { $1 @ [$2] }
  | /* empty */              { [] }

select_case:
  CASE select_pat ARROW LBRACE stmts RBRACE
    { { pat = $2; body = mk_stmt1 5 (Seq($5)) } }

select_pat:
  ID LPAREN opt_id_list RPAREN
    { { meth = $1; vars = $3 } }

opt_id_list:
    id_list { $1 }
  | /* empty */ { [] }

id_list:
    ID                   { [$1] }
  | id_list COMMA ID  { $1 @ [$3] }

select_timeout_opt:
    TIMEOUT INTLIT ARROW LBRACE stmts RBRACE
      { (Some $2, Some (mk_stmt1 5 (Seq $5))) }
  | /* empty */
      { (None, None) }

args:
  /* empty */    { [] }
  | arg_list     { $1 }

inits:
  | ID ASSIGN expr { [(mk_stmt1 1 (VarDecl($1, $3)))] }
  | ID ASSIGN expr COMMA inits { (mk_stmt1 1 (VarDecl($1, $3))) :: $5 }

expr:
  | FLOATLIT { mk_expr1 1 (Float $1) }
  | STRINGLIT { mk_expr1 1 (String $1) }
  | INTLIT { mk_expr1 1 (Int $1) }
  | ID { mk_expr1 1 (Var $1) }
  | SELF { mk_expr1 1 (Var "self") }
  | SENDER { mk_expr1 1 (Var "sender") }
  | expr PLUS expr { mk_expr1 2 (Binop ("+", $1, $3)) }
  | expr MINUS expr { mk_expr1 2 (Binop ("-", $1, $3)) }
  | expr TIMES expr { mk_expr1 2 (Binop ("*", $1, $3)) }
  | expr DIV expr { mk_expr1 2 (Binop ("/", $1, $3)) }
  | NEW ID LPAREN args RPAREN { mk_expr1 1 (New ($2, $4)) }
  | ID LPAREN args RPAREN { mk_expr1 1 (Call ($1, $3)) }
  | expr GE expr { mk_expr1 2 (Binop (">=", $1, $3)) }
  | expr LE expr { mk_expr1 2 (Binop ("<=", $1, $3)) }
  | expr GT expr { mk_expr1 2 (Binop (">", $1, $3)) }
  | expr LT expr { mk_expr1 2 (Binop ("<", $1, $3)) }
  | expr EQ  expr { mk_expr1 2 (Binop ("==", $1, $3)) }
  | expr NEQ expr { mk_expr1 2 (Binop ("!=", $1, $3)) }
  | LPAREN expr RPAREN { $2 }
