// Headless Node runner for the cooperative now/future/await sample.
//   node run_cooperative.mjs                          # mock AI (default)
//   GEMINI_API_KEY=... node run_cooperative.mjs       # real Gemini
//   ABCL_AI_PROVIDER=mock node run_cooperative.mjs    # force mock
//   node run_cooperative.mjs path/to/sample.abcl
import { createRequire } from "node:module";
import { readFileSync, writeFileSync, mkdtempSync, rmSync } from "node:fs";
import { execFileSync, execSync } from "node:child_process";
import { resolve, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { tmpdir } from "node:os";

const __dirname = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);

const ast = await import(resolve(__dirname, "src/ast.js"));
const { Runtime } = await import(resolve(__dirname, "src/runtime.js"));
const parser = require(resolve(__dirname, "src/parser/parser.js")).parser;
parser.yy = ast;

// ---- Real Gemini call (sync curl shell-out, mirrors OCaml's ai.ml) ----
function geminiCallSync(prompt, system, apiKey) {
  const dir = mkdtempSync(join(tmpdir(), "abcl_ai_"));
  const reqPath  = join(dir, "req.json");
  const respPath = join(dir, "resp.json");

  const body = {
    contents: [{ parts: [{ text: prompt }] }],
    generationConfig: { maxOutputTokens: 4096 },
  };
  if (system) body.systemInstruction = { parts: [{ text: system }] };
  writeFileSync(reqPath, JSON.stringify(body));

  const model = process.env.ABCL_AI_MODEL || "gemini-2.5-flash";
  const url =
    `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`;

  try {
    execFileSync("curl", [
      "-sf", "-X", "POST", url,
      "-H", "Content-Type: application/json",
      "-d", "@" + reqPath,
      "-o", respPath,
    ], { stdio: ["ignore", "ignore", "ignore"] });
    return execSync(
      `jq -r '.candidates[0].content.parts[0].text // .error.message // "<no response>"' ${respPath}`,
      { encoding: "utf8" }
    ).trim();
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

const file = process.argv[2] || "cooperative_now_future.abcl";
const src = readFileSync(resolve(__dirname, file), "utf8");
const tree = parser.parse(src);

const KEEP = /^\[(plan|answer|reviewer brief|verdict)\]/;
const rt = new Runtime((line) => {
  const s = String(line);
  if (KEEP.test(s)) console.log(s);
});

// Wire real Gemini if a key is present and provider isn't forced to mock.
const provider = (process.env.ABCL_AI_PROVIDER || "").toLowerCase();
const apiKey   = process.env.GEMINI_API_KEY;
if (provider !== "mock" && apiKey) {
  console.error("[ai] using Gemini (model=" + (process.env.ABCL_AI_MODEL || "gemini-2.5-flash") + ")");
  rt._aiCall = (prompt, system = null) => {
    try { return geminiCallSync(prompt, system, apiKey); }
    catch (e) {
      console.error("[ai] gemini failed, falling back to mock:", e.message);
      return `[mock-fallback] for: ${String(prompt).slice(0, 60)}`;
    }
  };
} else {
  console.error("[ai] using mock (set GEMINI_API_KEY to use Gemini)");
}

for (const cls of tree.classes) rt.registerClass(cls);
const topEnv = {};
for (const st of tree.statements) rt.evalStmt(st, topEnv);
