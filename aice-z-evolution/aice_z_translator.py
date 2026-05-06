#!/usr/bin/env python3
"""
AICE Z-evolution translator.

This tool intentionally lives outside the existing ABCL implementation tree.
It accepts an extended .aice meta file, derives a lightweight Z-style
specification, checks it through two logical projections, repairs simple
contradictions, runs a deterministic evolutionary selection model, and emits
an ABCL program that can drive AI agents to generate and verify target code.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import textwrap
from pathlib import Path
from typing import Iterable


@dataclasses.dataclass
class AiceSpec:
    name: str
    target_language: str
    task: str
    entities: list[str]
    state: list[str]
    invariants: list[str]
    operations: list[str]
    acceptance: list[str]
    generations: int
    reviewers: int
    mutation_rules: list[str]


@dataclasses.dataclass
class CheckResult:
    name: str
    ok: bool
    score: float
    findings: list[str]
    artifact: str


@dataclasses.dataclass
class Candidate:
    generation: int
    variant: str
    genome: dict[str, str]
    score: float
    findings: list[str]


def _strip_comments(src: str) -> str:
    return "\n".join(line.split("//", 1)[0] for line in src.splitlines())


def _find_name(src: str) -> str:
    m = re.search(r"\baice\s+([A-Za-z_][A-Za-z0-9_]*)\s*\{", src)
    return m.group(1) if m else "AiceZEvolution"


def _find_string(src: str, key: str, default: str = "") -> str:
    m = re.search(rf"\b{re.escape(key)}\s*=\s*\"((?:\\.|[^\"])*)\"", src, re.S)
    if not m:
        return default
    return bytes(m.group(1), "utf-8").decode("unicode_escape")


def _find_word(src: str, key: str, default: str = "") -> str:
    m = re.search(rf"\b{re.escape(key)}\s*=\s*([A-Za-z_][A-Za-z0-9_-]*)", src)
    return m.group(1) if m else default


def _find_int(src: str, key: str, default: int) -> int:
    m = re.search(rf"\b{re.escape(key)}\s+([0-9]+)\s*;", src)
    if not m:
        m = re.search(rf"\b{re.escape(key)}\s*=\s*([0-9]+)\s*;", src)
    return int(m.group(1)) if m else default


def _extract_block(src: str, name: str) -> str:
    m = re.search(rf"\b{re.escape(name)}\b\s*\{{", src)
    if not m:
        return ""
    start = m.end()
    depth = 1
    i = start
    while i < len(src) and depth:
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
        i += 1
    return src[start : i - 1]


def _extract_list(block: str, name: str) -> list[str]:
    inner = _extract_block(block, name)
    if not inner:
        return []
    items = []
    for m in re.finditer(r"\"((?:\\.|[^\"])*)\"\s*;", inner, re.S):
        items.append(bytes(m.group(1), "utf-8").decode("unicode_escape").strip())
    return items


def _extract_mutations(src: str) -> list[str]:
    rules = []
    for block in re.finditer(r"\brule\s+([A-Za-z_][A-Za-z0-9_]*)\s*\{(.*?)\}", src, re.S):
        name, body = block.group(1), block.group(2)
        target = _find_word(body, "target", "unknown")
        to = _find_word(body, "to", "")
        reason = _find_string(body, "reason", "")
        rules.append(f"{name}: set {target} to {to}. {reason}".strip())
    return rules


def parse_aice(path: Path) -> AiceSpec:
    src = _strip_comments(path.read_text(encoding="utf-8"))
    spec_block = _extract_block(src, "specification")
    formal_block = _extract_block(src, "formal_check")
    target = _find_word(src, "target_language", "ABCL")
    if target in {"default", "anything", "none"}:
        target = "any"
    return AiceSpec(
        name=_find_name(src),
        target_language=target,
        task=_find_string(src, "task", "Create a correct program from the formal specification."),
        entities=_extract_list(spec_block, "entities"),
        state=_extract_list(spec_block, "state"),
        invariants=_extract_list(spec_block, "invariants"),
        operations=_extract_list(spec_block, "operations"),
        acceptance=_extract_list(spec_block, "acceptance"),
        generations=_find_int(src, "generations", 4),
        reviewers=_find_int(formal_block or src, "reviewers", 3),
        mutation_rules=_extract_mutations(src),
    )


def z_identifier(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    return cleaned[:48] or "item"


def to_z_spec(spec: AiceSpec) -> str:
    entities = ", ".join(z_identifier(x) for x in spec.entities) or "Entity"
    state_lines = [f"  {z_identifier(s)} : VALUE" for s in spec.state] or ["  state : VALUE"]
    invariant_lines = [f"  {z_identifier(inv)}" for inv in spec.invariants] or ["  true"]
    op_lines = []
    for op in spec.operations:
        op_name = z_identifier(op)
        op_lines.append(
            "\n".join(
                [
                    f"{op_name}",
                    "  Delta SystemState",
                    "  input? : VALUE",
                    "  output! : VALUE",
                    f"  pre {z_identifier(op)}_pre",
                    f"  post {z_identifier(op)}_post",
                ]
            )
        )
    return "\n".join(
        [
            f"[{entities}, VALUE]",
            "",
            "SystemState",
            *state_lines,
            "where",
            *[f"  {line}" for line in invariant_lines],
            "",
            "\n\n".join(op_lines),
        ]
    ).strip()


NEGATION_PATTERNS = [
    (re.compile(r"\bmust\s+not\b", re.I), "must"),
    (re.compile(r"\bshall\s+not\b", re.I), "shall"),
    (re.compile(r"\bnever\b", re.I), "always"),
    (re.compile(r"\bnot\b", re.I), ""),
]


def normalize_predicate(text: str) -> tuple[str, bool]:
    lowered = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
    negated = False
    for pattern, replacement in NEGATION_PATTERNS:
        if pattern.search(lowered):
            negated = True
            lowered = pattern.sub(replacement, lowered)
    lowered = re.sub(r"\b(the|a|an|to|be|is|are|must|shall|should|always)\b", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered, negated


def detect_contradictions(items: Iterable[str]) -> list[str]:
    seen: dict[str, bool] = {}
    contradictions = []
    for item in items:
        key, negated = normalize_predicate(item)
        if not key:
            continue
        if key in seen and seen[key] != negated:
            contradictions.append(f"conflict on predicate '{key}'")
        seen[key] = negated
    return contradictions


def predicate_normal_form(spec: AiceSpec) -> CheckResult:
    items = spec.invariants + spec.operations + spec.acceptance
    contradictions = detect_contradictions(items)
    lines = []
    for i, item in enumerate(items, start=1):
        key, negated = normalize_predicate(item)
        prefix = "not " if negated else ""
        lines.append(f"P{i}: {prefix}{key}")
    coverage = min(1.0, len(items) / 8.0)
    score = 0.55 + coverage * 0.35 - len(contradictions) * 0.2
    return CheckResult(
        "predicate_normal_form",
        not contradictions,
        max(0.0, min(1.0, score)),
        contradictions or ["no direct predicate contradiction found"],
        "\n".join(lines),
    )


def state_transition_model(spec: AiceSpec) -> CheckResult:
    findings = []
    state_keys = {normalize_predicate(s)[0] for s in spec.state}
    for op in spec.operations:
        op_key = normalize_predicate(op)[0]
        if state_keys and not any(part in op_key for key in state_keys for part in key.split()[:2]):
            findings.append(f"operation may not mention tracked state: {op}")
    if not spec.operations:
        findings.append("no operations specified")
    if not spec.invariants:
        findings.append("no invariants specified")
    ok = not any(f.startswith("no ") for f in findings)
    score = 0.75 if ok else 0.45
    score -= min(0.3, 0.04 * len(findings))
    artifact = "\n".join(
        [f"S{i}: {s}" for i, s in enumerate(spec.state, start=1)]
        + [f"T{i}: {op}" for i, op in enumerate(spec.operations, start=1)]
        + [f"I{i}: preserved({inv})" for i, inv in enumerate(spec.invariants, start=1)]
    )
    return CheckResult(
        "state_transition_model",
        ok,
        max(0.0, min(1.0, score)),
        findings or ["all transitions have enough structure for preservation checks"],
        artifact,
    )


def z_schema_review(spec: AiceSpec, z_spec: str) -> CheckResult:
    findings = []
    if "SystemState" not in z_spec:
        findings.append("missing SystemState schema")
    if not spec.acceptance:
        findings.append("no acceptance conditions for final program verification")
    if spec.target_language == "any":
        findings.append("target language left open by design")
    score = 0.82 - 0.08 * len([f for f in findings if not f.endswith("by design")])
    return CheckResult(
        "z_schema_review",
        not any(not f.endswith("by design") for f in findings),
        max(0.0, min(1.0, score)),
        findings or ["Z schema is structurally complete"],
        z_spec,
    )


def repair_spec(spec: AiceSpec, findings: list[str]) -> AiceSpec:
    if not findings:
        return spec
    repaired_invariants = []
    seen: dict[str, bool] = {}
    for item in spec.invariants:
        key, negated = normalize_predicate(item)
        if key in seen and seen[key] != negated:
            repaired_invariants.append(
                f"REPAIRED CONSENSUS: prefer satisfiable safety form for {key}"
            )
            seen[key] = False
        else:
            repaired_invariants.append(item)
            seen[key] = negated
    return dataclasses.replace(spec, invariants=repaired_invariants)


def evolve(spec: AiceSpec, checks: list[CheckResult]) -> list[Candidate]:
    base_score = sum(c.score for c in checks) / len(checks)
    variants = ["minimal", "auditable", "defensive"]
    winners = []
    genome = {
        "target_language": spec.target_language,
        "formal_basis": "Z + predicate_normal_form + state_transition_model",
        "verification": "three_reviewers_then_best",
        "repair": "logical_consensus",
    }
    for generation in range(1, max(1, spec.generations) + 1):
        scored = []
        for i, variant in enumerate(variants):
            mutation_bonus = min(0.18, 0.025 * generation + 0.015 * i)
            audit_bonus = 0.05 if variant == "auditable" and generation >= 2 else 0.0
            defensive_bonus = 0.07 if variant == "defensive" and generation >= 3 else 0.0
            score = min(1.0, base_score + mutation_bonus + audit_bonus + defensive_bonus)
            child = dict(genome)
            child["style"] = variant
            child["generation"] = str(generation)
            if generation <= len(spec.mutation_rules):
                child["mutation"] = spec.mutation_rules[generation - 1]
            scored.append(Candidate(generation, variant, child, score, []))
        winner = max(scored, key=lambda c: c.score)
        winners.append(winner)
        genome = winner.genome
    return winners


def abcl_string(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def emit_abcl(spec: AiceSpec, z_spec: str, checks: list[CheckResult], winners: list[Candidate]) -> str:
    target = spec.target_language if spec.target_language != "any" else "any suitable language"
    reviewer_count = max(3, spec.reviewers)
    checks_text = "\n\n".join(
        f"[{c.name}] ok={c.ok} score={c.score:.2f}\n{c.artifact}\nfindings: {'; '.join(c.findings)}"
        for c in checks
    )
    final_genome = json.dumps(winners[-1].genome if winners else {}, ensure_ascii=False, indent=2)
    task = (
        spec.task
        + "\n\nTarget language: "
        + target
        + "\n\nFormal Z specification:\n"
        + z_spec
        + "\n\nLogical check artifacts:\n"
        + checks_text
        + "\n\nFinal genome:\n"
        + final_genome
        + "\n\nGenerate a complete program, then check it against the Z specification and acceptance conditions."
    )
    return f"""// Generated from {spec.name}.aice by aice_z_translator.py
// Runtime: OCaml ABCL/c+ (src/repl_thread.ml / abclrepl_thread).
// Pipeline: initial specification -> Z -> two logical checks -> {reviewer_count} reviewers -> evolutionary repair/selection -> final program verification.

class EvolutionCoordinator {{
  var z_spec = {abcl_string(z_spec)};
  var logical_checks = {abcl_string(checks_text)};
  var persona = "You generate production-quality programs from formal Z-style specifications. Prefer OCaml ABCL/c+ actor syntax unless the target language is explicitly not ABCL. Return only the requested program and concise verification notes.";
  var reviewer_persona = "You are a formal methods reviewer for OCaml ABCL/c+. Check whether the candidate program satisfies the Z specification, predicate normal form, state transition model, and acceptance conditions. Return PASS or FAIL first, then the most important reason.";

  method run() {{
    var prompt = {abcl_string(task)};

    print("=== Z SPEC ===");
    print(z_spec);
    print("=== LOGICAL CHECKS ===");
    print(logical_checks);

    var candidate = ai_call_with_system(persona, prompt);
    print("=== GENERATED PROGRAM ===");
    print(candidate);

    var payload = "Z SPEC:\\n" + z_spec + "\\n\\nCHECKS:\\n" + logical_checks + "\\n\\nPROGRAM:\\n" + candidate;
    var r1 = ai_call_with_system(reviewer_persona, payload);
    var r2 = ai_call_with_system(reviewer_persona, payload);
    var r3 = ai_call_with_system(reviewer_persona, payload);

    print("=== FINAL FORMAL REVIEWS ===");
    print(r1);
    print(r2);
    print(r3);
    print("=== DECISION ===");
    print("Select the candidate only when the three reviews agree on PASS or when the best logical review gives a repairable issue.");
    print(ai_usage());
  }}
}}

var coordinator = new EvolutionCoordinator();
send coordinator.run();
"""


def write_outputs(input_path: Path, out_dir: Path) -> dict[str, str]:
    spec = parse_aice(input_path)
    z_spec = to_z_spec(spec)
    initial_checks = [
        z_schema_review(spec, z_spec),
        predicate_normal_form(spec),
        state_transition_model(spec),
    ]
    contradictions = []
    for c in initial_checks:
        contradictions.extend([f"{c.name}: {f}" for f in c.findings if "conflict" in f])
    repaired = repair_spec(spec, contradictions)
    if repaired != spec:
        z_spec = to_z_spec(repaired)
    checks = [
        z_schema_review(repaired, z_spec),
        predicate_normal_form(repaired),
        state_transition_model(repaired),
    ]
    winners = evolve(repaired, checks)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = input_path.stem
    abcl_path = out_dir / f"{stem}.abcl"
    report_path = out_dir / f"{stem}.report.md"
    manifest_path = out_dir / f"{stem}.manifest.json"
    abcl_path.write_text(emit_abcl(repaired, z_spec, checks, winners), encoding="utf-8")
    best_check = max(checks, key=lambda c: c.score)
    report = [
        f"# {spec.name} translation report",
        "",
        f"- Target language: `{repaired.target_language}`",
        f"- Generations: `{repaired.generations}`",
        f"- Reviewers: `{max(3, repaired.reviewers)}`",
        f"- Best initial logical view: `{best_check.name}` score `{best_check.score:.2f}`",
        f"- Contradiction repair: `{'applied' if repaired != spec else 'not_needed'}`",
        "",
        "## Z Specification",
        "",
        "```z",
        z_spec,
        "```",
        "",
        "## Checks",
        "",
    ]
    for c in checks:
        report.extend([f"### {c.name}", "", f"- ok: `{c.ok}`", f"- score: `{c.score:.2f}`"])
        report.extend(f"- {f}" for f in c.findings)
        report.append("")
    report.extend(["## Winners", ""])
    for w in winners:
        report.append(f"- generation {w.generation}: `{w.variant}` score `{w.score:.2f}`")
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    manifest = {
        "name": spec.name,
        "runtime": "ocaml_abcl_cplus",
        "input": str(input_path),
        "abcl": str(abcl_path),
        "report": str(report_path),
        "target_language": repaired.target_language,
        "checks": [dataclasses.asdict(c) for c in checks],
        "winners": [dataclasses.asdict(w) for w in winners],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"abcl": str(abcl_path), "report": str(report_path), "manifest": str(manifest_path)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Translate extended .aice files to ABCL with Z-based evolutionary verification.")
    parser.add_argument("input", type=Path)
    parser.add_argument("-o", "--out-dir", type=Path, default=Path("aice-z-evolution/out"))
    args = parser.parse_args()
    outputs = write_outputs(args.input, args.out_dir)
    for kind, path in outputs.items():
        print(f"{kind}: {path}")


if __name__ == "__main__":
    main()
