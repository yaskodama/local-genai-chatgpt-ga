%lex
%%
\s+                             /* skip */
"//"[^\n]*                      /* skip line comments */
"class"      return 'CLASS';
"method"     return 'METHOD';
"var"        return 'VAR';
"call"       return 'CALL';
"if"         return 'IF';
"else"       return 'ELSE';
"send!"      return 'UNSAFESEND';
"send"       return 'SEND';
"now"        return 'NOW';
"future"     return 'FUTURE';
"await"      return 'AWAIT';
"print"      return 'PRINT';
"reply"      return 'REPLY';
"new"        return 'NEW';
"select"     return 'SELECT';
"case"       return 'CASE';
"timeout"    return 'TIMEOUT';
"->"         return 'ARROW';
"=="         return 'EQ';
"!="         return 'NEQ';
"<="         return 'LE';
">="         return 'GE';
"{"  return '{';
"}"  return '}';
"("  return '(';
")"  return ')';
";"  return ';';
","  return ',';
"."  return '.';
"="  return '=';
"<"  return 'LT';
">"  return 'GT';
"+"  return '+';
"-"  return '-';
"*"  return '*';
"/"  return '/';
[0-9]+\.[0-9]*   return 'FLOAT';
[0-9]+\b         return 'INT';
\"[^\"]*\"       return 'STRING';
[a-zA-Z_][a-zA-Z0-9_]*  return 'IDENT';
<<EOF>>          return 'EOF';
/lex

%start program
%left EQ NEQ LT GT LE GE
%left '+' '-'
%left '*' '/'

%{
/* keep empty: use yy.X in actions */
%}

%%

program
  : class_decls stmts EOF
      { return yy.Program($1, $2); }
  ;

class_decls
  : class_decls class_decl
      { $$ = $1.concat([$2]); }
  |
      { $$ = []; }
  ;

class_decl
  : CLASS IDENT '{' class_members '}'
      {
        var fields  = $4.filter(function(m){ return m.type === 'VarField'; });
        var methods = $4.filter(function(m){ return m.type === 'MethodDecl'; });
        $$ = yy.ClassDecl($2, methods, fields);
      }
  ;

class_members
  : class_members class_member
      { $$ = $1.concat([$2]); }
  |
      { $$ = []; }
  ;

class_member
  : method_decl
      { $$ = $1; }
  | VAR IDENT '=' expr ';'
      { $$ = yy.VarField($2, $4); }
  ;

method_decl
  : METHOD IDENT '(' params ')' '{' stmts '}'
      { $$ = yy.MethodDecl($2, $4, yy.Seq($7)); }
  ;

params
  : IDENT
      { $$ = [$1]; }
  | params ',' IDENT
      { $$ = $1.concat([$3]); }
  |
      { $$ = []; }
  ;

stmts
  : stmts stmt
      { $$ = $1.concat([$2]); }
  |
      { $$ = []; }
  ;

stmt
  : VAR IDENT '=' expr ';'                       { $$ = yy.VarDecl($2, $4); }
  | IDENT '=' expr ';'                           { $$ = yy.Assign($1, $3); }
  | SEND IDENT '.' IDENT '(' args ')' ';'        { $$ = yy.Send($2, $4, $6, false); }
  | UNSAFESEND IDENT '.' IDENT '(' args ')' ';'  { $$ = yy.Send($2, $4, $6, true); }
  | PRINT '(' expr ')' ';'                       { $$ = yy.Print($3); }
  | REPLY '(' expr ')' ';'                       { $$ = yy.Reply($3); }
  | CALL IDENT '(' args ')' ';'                  { $$ = yy.CallStmt($2, $4); }
  | IDENT '(' args ')' ';'                       { $$ = yy.CallStmt($1, $3); }
  | IF '(' expr ')' '{' stmts '}' else_opt       { $$ = yy.If($3, yy.Seq($6), $8); }
  | SELECT '{' select_cases timeout_opt '}'      { $$ = yy.Select($3, $4.ms, $4.body); }
  ;

else_opt
  : ELSE '{' stmts '}'
      { $$ = yy.Seq($3); }
  |
      { $$ = null; }
  ;

select_cases
  : select_cases select_case
      { $$ = $1.concat([$2]); }
  | select_case
      { $$ = [$1]; }
  ;

select_case
  : CASE IDENT '(' params ')' ARROW '{' stmts '}'
      { $$ = yy.SelectCase($2, $4, yy.Seq($8)); }
  ;

timeout_opt
  : TIMEOUT INT ARROW '{' stmts '}'
      { $$ = { ms: Number($2), body: yy.Seq($5) }; }
  |
      { $$ = { ms: null, body: null }; }
  ;

args
  : expr
      { $$ = [$1]; }
  | args ',' expr
      { $$ = $1.concat([$3]); }
  |
      { $$ = []; }
  ;

expr
  : INT                       { $$ = yy.IntLit(Number(yytext)); }
  | FLOAT                     { $$ = yy.FloatLit(parseFloat(yytext)); }
  | STRING                    { $$ = yy.StringLit(yytext.slice(1, -1)); }
  | IDENT                     { $$ = yy.Var($1); }
  | NEW IDENT '(' args ')'    { $$ = yy.NewExpr($2, $4); }
  | IDENT '(' args ')'        { $$ = yy.CallExpr($1, $3); }
  | NOW IDENT '.' IDENT '(' args ')'    { $$ = yy.Now($2, $4, $6); }
  | FUTURE IDENT '.' IDENT '(' args ')' { $$ = yy.Future($2, $4, $6); }
  | AWAIT expr                          { $$ = yy.Await($2); }
  | '(' expr ')'              { $$ = $2; }
  | expr '+' expr             { $$ = yy.Binop('+', $1, $3); }
  | expr '-' expr             { $$ = yy.Binop('-', $1, $3); }
  | expr '*' expr             { $$ = yy.Binop('*', $1, $3); }
  | expr '/' expr             { $$ = yy.Binop('/', $1, $3); }
  | expr EQ  expr             { $$ = yy.Binop('==', $1, $3); }
  | expr NEQ expr             { $$ = yy.Binop('!=', $1, $3); }
  | expr LT  expr             { $$ = yy.Binop('<',  $1, $3); }
  | expr GT  expr             { $$ = yy.Binop('>',  $1, $3); }
  | expr LE  expr             { $$ = yy.Binop('<=', $1, $3); }
  | expr GE  expr             { $$ = yy.Binop('>=', $1, $3); }
  ;
