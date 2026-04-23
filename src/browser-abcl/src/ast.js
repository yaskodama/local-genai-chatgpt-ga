export function Program(classes = [], statements = []) {
  return { type: "Program", classes, statements };
}

export function ClassDecl(name, methods, fields = []) {
  return { type: "ClassDecl", name, methods, fields };
}

export function VarField(name, expr) {
  return { type: "VarField", name, expr };
}

export function MethodDecl(name, params, body) {
  return { type: "MethodDecl", name, params, body };
}

export function Seq(statements) {
  return { type: "Seq", statements };
}

export function VarDecl(name, expr) {
  return { type: "VarDecl", name, expr };
}

export function Assign(name, expr) {
  return { type: "Assign", name, expr };
}

export function Send(target, method, args, unsafe = false) {
  return { type: "Send", target, method, args, unsafe };
}

export function Print(expr) {
  return { type: "Print", expr };
}

export function Reply(expr) {
  return { type: "Reply", expr };
}

export function CallStmt(name, args) {
  return { type: "CallStmt", name, args };
}

export function NewExpr(className, args = []) {
  return { type: "NewExpr", className, args };
}

export function Var(name) {
  return { type: "Var", name };
}

export function IntLit(value) {
  return { type: "IntLit", value };
}

export function FloatLit(value) {
  return { type: "FloatLit", value };
}

export function StringLit(value) {
  return { type: "StringLit", value };
}

export function Binop(op, left, right) {
  return { type: "Binop", op, left, right };
}

export function CallExpr(name, args) {
  return { type: "CallExpr", name, args };
}

export function If(cond, thenBody, elseBody) {
  return { type: "If", cond, thenBody, elseBody };
}

export function Select(cases, timeoutMs = null, timeoutBody = null) {
  return { type: "Select", cases, timeoutMs, timeoutBody };
}

export function SelectCase(method, params, body) {
  return { type: "SelectCase", method, params, body };
}
