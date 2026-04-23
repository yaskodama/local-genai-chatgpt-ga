import { Runtime } from "./runtime.js";

export class Interpreter {
  constructor(printer) {
    this.runtime = new Runtime(printer);
  }

  setCanvas(canvas) {
    this.runtime.setCanvas(canvas);
  }

  runProgram(ast) {
    this.runtime.reset();
    for (const cls of ast.classes) {
      this.runtime.registerClass(cls);
    }
    for (const st of ast.statements) {
      this.runtime.evalStmt(st, {});
    }
    // Start all actor threads (setTimeout-based)
    this.runtime.scheduleAllActors();
  }
}
