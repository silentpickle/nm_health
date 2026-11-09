"""The complexity guard and catalog (docs/COMPLEXITY.md). Complexity is ruff's C901 (mccabe: branches and loops); nesting is
how many blocks (if, for, while, try, with, match) sit inside one another in a function, counted the way pylint does
(an elif chain is one level).

  .venv/bin/python scripts/complexity.py                 # the guard (hygiene.sh, so every commit and CI)
  .venv/bin/python scripts/complexity.py --update        # rewrite the baseline from the code as it is now
  .venv/bin/python scripts/complexity.py --catalog       # every function over SOFT, ranked, with its risk tier
  .venv/bin/python scripts/complexity.py --catalog --worst 10 --out reports/complexity/catalog.md

Owner 2026-10-12: "complexity under 15 where possible (hard limit of 20); avoid nesting deeper than 2 levels by using
guard clauses and early returns." Existing functions are fine for now. So, for a function not in the baseline:
  - complexity over HARD (20) fails; over SOFT (15) warns; nesting deeper than DEPTH (2) warns.
  - A renamed or moved function counts as new.
A function in the baseline may stay or shrink, never grow: growth fails (GROWTH_FAILS; owner 2026-10-20).
The baseline (.complexity_baseline.json) is every function over SOFT and every one nesting deeper than DEPTH, keyed
"path::name"; two functions with one name in one file (methods, nested helpers) are a list. Raising an entry by hand is a
reviewed edit. Generic on purpose: no house_walkthrough paths outside RISK. Copy it to another Python project with ruff.
"""
import argparse, ast, json, re, shutil, subprocess, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ".complexity_baseline.json"
HARD, SOFT, DEPTH = 20, 15, 2
GROWTH_FAILS = True           # owner 2026-10-20: "flip it" (orders grew 20 -> 22 on a warning nobody saw, #137)
# Risk tiers for the catalog, first match wins: where a refactor is cheapest to get wrong comes first in the plan.
TIERS = ["low", "product", "money"]      # the order the plan takes them in
RISK = [
    ("money", r"^portal/selftest_(accounting|buyflow_e2e|money_\w+|payments|billing|holds|limits)\.py$"),   # the money safety net
    ("low", r"(^|/)(selftest_|test_)[^/]*\.py$|^(evals|scripts|docs|reports|shelved)/|^portal/(mock|devtools|chaos|analytics)\.py$"),
    ("money", r"^portal/(accounting|accounting_live|billing|payments|price_list|pricing|spend|holds|remake|extras|care|review)\.py$"),
    ("product", r"."),
]
MSG = re.compile(r"`(?P<name>.+)` is too complex \((?P<score>\d+) > \d+\)")
BLOCKS = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With, ast.AsyncWith, ast.Match) + \
    ((ast.TryStar,) if hasattr(ast, "TryStar") else ())
FUNCS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)


def ruff(root, *args):
    local = ROOT / ".venv" / "bin" / "ruff"
    exe = str(local) if local.exists() else (shutil.which("ruff") or sys.exit("complexity: ruff not found"))
    p = subprocess.run([exe, *args], cwd=root, capture_output=True, text=True, check=False)
    if p.returncode:
        sys.exit(f"complexity: ruff failed\n{p.stderr}")
    return p.stdout


def rel(root, f):
    return Path(f).resolve().relative_to(root.resolve()).as_posix()


def complexity(root):
    """[(path, line, name, score)] for every function scoring over SOFT (ruff's own excludes apply)."""
    out = ruff(root, "check", "--select", "C901", "--config", f"lint.mccabe.max-complexity={SOFT}", "--ignore-noqa",
               "--output-format", "json", "--exit-zero", "--no-cache", ".")
    found = [(d, MSG.search(d["message"])) for d in json.loads(out or "[]")]
    return [(rel(root, d["filename"]), d["location"]["row"], m["name"], int(m["score"])) for d, m in found if m]


def depth(node, level=0):
    """The deepest block nesting under node, not counting nested functions or classes (they're measured on their own)."""
    deepest = level
    for child in ast.iter_child_nodes(node):
        if isinstance(child, FUNCS):
            continue
        elif_chain = isinstance(node, ast.If) and child in node.orelse and len(node.orelse) == 1 and isinstance(child, ast.If)
        step = 1 if isinstance(child, BLOCKS) and not elif_chain else 0
        deepest = max(deepest, depth(child, level + step))
    return deepest


def nesting(root):
    """[(path, line, name, depth)] for every function nesting deeper than DEPTH, in the files ruff checks."""
    out = []
    for f in ruff(root, "check", "--show-files", "--no-cache", ".").split():
        if not f.endswith(".py"):
            continue
        try:
            tree = ast.parse((root / f).read_text(), f)
        except (SyntaxError, UnicodeDecodeError):
            continue                                     # ruff's own check reports these
        out += [(rel(root, root / f), n.lineno, n.name, d) for n in ast.walk(tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and (d := depth(n)) > DEPTH]
    return out


def keyed(found):
    by = defaultdict(list)
    for path, _, name, value in found:
        by[f"{path}::{name}"].append(value)
    return {k: sorted(v, reverse=True) for k, v in sorted(by.items())}


def compare(base, now):
    """(new, grown, stale): new = (key, value) with no baseline entry for it; grown = (key, old, new) that went up;
    stale = keys that went down or away (--update locks the lower number in)."""
    new = [(k, v) for k, vs in now.items() for v in vs[len(base.get(k, [])):]]
    grown = [(k, o, v) for k, vs in now.items() for o, v in zip(base.get(k, []), vs) if v > o]
    stale = [k for k, old in base.items() if len(now.get(k, [])) < len(old) or any(v < o for o, v in zip(old, now.get(k, [])))]
    return new, grown, stale


def report(metric, base, now):
    """Print what changed for one metric; return how many failures."""
    new, grown, stale = compare(base, now)
    fails = 0
    for k, v in new:
        if metric == "complexity" and v > HARD:
            fails += 1
            print(f"complexity: FAIL {k} scores {v} (hard limit {HARD}). Split it: one small function per case, rule or step")
        elif metric == "complexity":
            print(f"complexity: warning: {k} scores {v} (aim for {SOFT} or under)")
        else:
            print(f"complexity: warning: {k} nests {v} deep (aim for {DEPTH}: guard clauses and early returns)")
    for k, o, v in grown:
        fails += GROWTH_FAILS
        print(f"complexity: {'GREW' if GROWTH_FAILS else 'warning: grew'} {k} {metric} {o} -> {v}")
    return fails, len(stale)


def measure(root):
    return {"complexity": keyed(complexity(root)), "nesting": keyed(nesting(root))}


def guard(root, path):
    base = json.loads(path.read_text()) if path.exists() else {}
    now = measure(root)
    fails = stale = 0
    for metric, cur in now.items():
        f, s = report(metric, base.get(metric, {}), cur)
        fails, stale = fails + f, stale + s
    if stale:
        print(f"complexity: {stale} function(s) got simpler; scripts/complexity.py --update locks that in")
    if not fails:
        print(f"complexity: ok (nothing new over {HARD}; {sum(map(len, base.get('complexity', {}).values()))} older functions "
              f"over {SOFT} and {sum(map(len, base.get('nesting', {}).values()))} nesting deeper than {DEPTH} in the baseline)")
    return 1 if fails else 0


def update(root, path):
    now = measure(root)
    blocks = []
    for metric, cur in now.items():                       # one function per line: small diffs
        rows = ",\n".join(f"  {json.dumps(k)}: {json.dumps(v)}" for k, v in cur.items())
        blocks.append(f'"{metric}": {{\n{rows}\n}}')
    head = f'"limits": {{"hard": {HARD}, "soft": {SOFT}, "depth": {DEPTH}}}, "tool": "ruff C901 (mccabe) + ast nesting"'
    path.write_text("{" + head + ",\n" + ",\n".join(blocks) + "}\n")
    print(f"complexity: baseline written, {sum(map(len, now['complexity'].values()))} over {SOFT}, "
          f"{sum(map(len, now['nesting'].values()))} nesting deeper than {DEPTH}")


def tier(path):
    return next(t for t, rx in RISK if re.search(rx, path))


def table(rows):
    link = lambda p, ln, n: f"[{p}:{ln}]({p}:{ln}) `{n}`"   # noqa: E731
    return ["| Score | Nesting | Tier | Function |", "|---|---|---|---|"] + \
        [f"| {s}{' ⛔' if s > HARD else ''} | {d} | {t} | {link(p, ln, n)} |" for s, d, t, p, ln, n in rows]


def catalog(root, worst):
    deep = {(p, ln): d for p, ln, _, d in nesting(root)}
    rows = sorted(((s, deep.get((p, ln), "≤2"), tier(p), p, ln, n) for p, ln, n, s in complexity(root)), key=lambda r: -r[0])
    n_worst = max(1, round(len(rows) * worst / 100)) if rows else 0
    nxt = sorted(rows, key=lambda r: (TIERS.index(r[2]), -r[0]))[:n_worst]
    out = ["# Complexity catalog", "",
           f"`scripts/complexity.py --catalog --worst {worst:g}`: every function scoring over {SOFT} (ruff C901; ⛔ over the "
           f"hard limit {HARD}). {len(rows)} functions; " + ", ".join(f"{t} {sum(r[2] == t for r in rows)}" for t in TIERS) +
           f". {len(deep)} functions nest deeper than {DEPTH}.", "",
           f"## Worst {worst:g}% ({n_worst})", "", *table(rows[:n_worst]), "",
           f"## Next up: lowest risk first, then highest score ({n_worst})", "", *table(nxt), "", "## All, by tier", ""]
    for t in TIERS:
        tr = [r for r in rows if r[2] == t]
        out += [f"### {t} ({len(tr)})", "", *table(tr), ""]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="The complexity guard and catalog (docs/COMPLEXITY.md).")
    ap.add_argument("--update", action="store_true", help="rewrite the baseline from the code as it is now")
    ap.add_argument("--catalog", action="store_true", help=f"markdown list of every function over {SOFT}")
    ap.add_argument("--worst", type=float, default=10, help="catalog: the top N percent (default 10)")
    ap.add_argument("--out", help="catalog: write here instead of printing")
    ap.add_argument("--root", default=str(ROOT), help="the project to measure (default: this repo)")
    a = ap.parse_args()
    root = Path(a.root)
    if a.update:
        return update(root, root / BASELINE)
    if not a.catalog:
        return guard(root, root / BASELINE)
    text = catalog(root, a.worst)
    if not a.out:
        print(text)
        return 0
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
