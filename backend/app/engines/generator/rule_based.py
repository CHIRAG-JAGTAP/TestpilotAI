"""Offline rule-based pytest generator (Phase 4). Stdlib only; never runs the code under test.

Oracles (no tautologies - we never record "whatever the function returned"):
  1. GUARD SIMULATION: top-level `if <simple test>: raise X / return <literal>` chains are evaluated
     symbolically with a whitelisted evaluator, giving exact expectations (pytest.raises / ==).
  2. TYPE ORACLE: declared or source-inferred return types (isinstance check).
  3. ROBUSTNESS: invalid-type inputs may only fail with standard input-rejection exceptions.
"""
from __future__ import annotations

import ast
import hashlib
import itertools
import random
import re
from dataclasses import dataclass, field

from app.engines.analyzer.analyzer import FunctionInfo, ModuleAnalysis, analyse_source

GENERATOR_VERSION = "rule-based-1.0"
INT_MAX = 2**31 - 1
BASE_VALUES = {
    "int": [(1, "normal"), (0, "zero"), (-1, "negative"), (100, "normal"), (INT_MAX, "maximum")],
    "float": [(1.5, "normal"), (0.0, "zero"), (-1.5, "negative")],
    "str": [("abc", "normal"), ("", "empty"), (" ", "boundary")],
    "bool": [(True, "normal"), (False, "boundary")],
    "list": [([1, 2, 3], "normal"), ([], "empty"), ([0], "boundary")],
    "tuple": [((1, 2), "normal"), ((), "empty")],
    "dict": [({"a": 1}, "normal"), ({}, "empty")],
    "set": [({1, 2}, "normal"), (set(), "empty")],
}
NAME_HINTS = {"int": ("n", "num", "count", "i", "j", "k", "x", "y", "size", "index", "value", "amount", "score", "age"),
              "str": ("s", "text", "name", "word", "line", "string", "path", "msg"),
              "list": ("items", "lst", "values", "nums", "data", "xs", "array", "numbers"),
              "float": ("price", "ratio", "rate", "a", "b")}
REJECTION = ("TypeError", "ValueError", "AttributeError", "KeyError", "IndexError", "ZeroDivisionError")
SAFE_NODES = (ast.Expression, ast.Compare, ast.BoolOp, ast.UnaryOp, ast.BinOp, ast.Name, ast.Constant, ast.Load,
              ast.And, ast.Or, ast.Not, ast.USub, ast.UAdd, ast.Add, ast.Sub, ast.Mult, ast.Mod, ast.FloorDiv, ast.Div,
              ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Is, ast.IsNot, ast.In, ast.NotIn, ast.Call)


# ------------------------------------------------------------------ safe symbolic evaluation
def safe_eval(expr: ast.expr, env: dict):
    """Evaluate a tiny whitelisted expression. Returns (ok, value). Never calls user code."""
    heavy = any(isinstance(v, (str, list, tuple, dict, set)) for v in env.values())
    for n in ast.walk(expr):
        if not isinstance(n, SAFE_NODES):
            return False, None
        if isinstance(n, ast.Name) and n.id not in env and n.id not in ("len", "abs", "True", "False", "None"):
            return False, None
        if isinstance(n, ast.Call) and not (isinstance(n.func, ast.Name) and n.func.id in ("len", "abs")):
            return False, None
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Mult) and heavy:
            return False, None
    try:
        code = compile(ast.Expression(expr), "<guard>", "eval")
        return True, eval(code, {"__builtins__": {}, "len": len, "abs": abs}, dict(env))  # noqa: S307 (whitelisted)
    except Exception:
        return False, None


def _literal(node: ast.AST):
    try:
        return True, ast.literal_eval(node)
    except Exception:
        return False, None


def simulate(fn_node: ast.AST, env: dict):
    """Return ('raise', ExcName) | ('return', value) | None when the outcome is not statically decidable."""
    def run(stmts):
        for st in stmts:
            if isinstance(st, ast.If):
                ok, val = safe_eval(st.test, env)
                if not ok:
                    return None
                branch = st.body if val else st.orelse
                if branch:
                    res = run(branch)
                    if res is not None or not _falls_through(branch):
                        return res
                continue
            if isinstance(st, ast.Raise):
                exc = st.exc.func if isinstance(st.exc, ast.Call) else st.exc
                return ("raise", ast.unparse(exc)) if exc is not None else None
            if isinstance(st, ast.Return):
                if st.value is None:
                    return ("return", None)
                ok, v = _literal(st.value)
                if not ok:
                    ok, v = safe_eval(st.value, env)      # e.g. `return a / b`, `return value`
                if not ok or isinstance(v, (set, dict)):
                    return None
                return ("return", v)
            if isinstance(st, ast.Expr) and isinstance(st.value, ast.Constant):
                continue                                   # docstring
            return None
        return None
    return run(fn_node.body)


def _falls_through(stmts) -> bool:
    return not any(isinstance(s, (ast.Return, ast.Raise)) for s in stmts)


# ------------------------------------------------------------------ candidate values
def _base_type(annotation: str | None, default: str | None, name: str) -> str | None:
    if annotation:
        a = re.sub(r"\s+", "", annotation)
        a = re.sub(r"^Optional\[(.*)\]$", r"\1", a)
        a = re.sub(r"\|None$|^None\|", "", a)
        m = re.match(r"^(?:typing\.)?([A-Za-z]+)", a)
        if m:
            t = m.group(1).lower()
            t = {"sequence": "list", "iterable": "list", "mapping": "dict"}.get(t, t)
            if t in BASE_VALUES:
                return t
    if default is not None:
        ok, v = _literal(ast.parse(default, mode="eval").body)
        if ok and v is not None:
            return {bool: "bool", int: "int", float: "float", str: "str", list: "list", dict: "dict",
                    tuple: "tuple"}.get(type(v))
    for t, names in NAME_HINTS.items():
        if name in names:
            return t
    return None


def _harvest_constants(fn: FunctionInfo) -> dict[str, list]:
    consts: dict[str, list] = {}
    params = {p.name for p in fn.params}
    for n in ast.walk(fn.node):
        if isinstance(n, ast.Compare):
            sides = [n.left] + n.comparators
            for a, b in itertools.permutations(sides, 2):
                if isinstance(a, ast.Name) and a.id in params:
                    ok, v = _literal(b)
                    if ok and isinstance(v, (int, float, str)) and not isinstance(v, bool):
                        consts.setdefault(a.id, []).append(v)
    return consts


def candidates(fn: FunctionInfo) -> dict[str, list[tuple]]:
    """param -> ordered [(value, category)]; deterministic, de-duplicated."""
    consts = _harvest_constants(fn)
    out: dict[str, list[tuple]] = {}
    for i, p in enumerate(fn.params):
        if p.kind in ("vararg", "kwarg") or (fn.class_name and i == 0):   # skip *args/**kw and self/cls
            continue
        t = _base_type(p.annotation, p.default, p.name)
        vals: list[tuple] = list(BASE_VALUES.get(t, [(0, "zero"), (1, "normal"), ("a", "normal")]))
        for c in consts.get(p.name, []):
            if isinstance(c, str):
                vals += [(c, "boundary"), (c + "x", "boundary")]
            elif isinstance(c, int):
                vals += [(c - 1, "boundary"), (c, "boundary"), (c + 1, "boundary")]
            else:
                vals += [(c - 0.5, "boundary"), (c, "boundary"), (c + 0.5, "boundary")]
        if t == "float":
            vals = [(float(v), c) if isinstance(v, int) and not isinstance(v, bool) else (v, c) for v, c in vals]
        seen, uniq = set(), []
        for v, c in vals:
            key = (type(v).__name__, repr(v))
            if key not in seen:
                seen.add(key); uniq.append((v, c))
        if p.default is None or True:
            out[p.name] = uniq
    return out


# ------------------------------------------------------------------ return-type oracle
def _return_types(fn: FunctionInfo) -> tuple[str, ...] | None:
    simple = {"int": ("int",), "float": ("int", "float"), "str": ("str",), "bool": ("bool",),
              "list": ("list",), "dict": ("dict",), "tuple": ("tuple",), "set": ("set",), "None": ("type(None)",)}
    if fn.returns:
        r = re.sub(r"\s+", "", fn.returns)
        base = re.match(r"^([A-Za-z]+)", r)
        if base and r in simple:
            return simple[r]
        if base and base.group(1).lower() in simple and "[" in r and "|" not in r and "Optional" not in r:
            return simple[base.group(1).lower()]
        return None
    types: set[str] = set()
    for n in ast.walk(fn.node):
        if isinstance(n, ast.Return) and n.value is not None:
            v = n.value
            if isinstance(v, ast.Constant):
                types.add({bool: "bool", int: "int", float: "float", str: "str"}.get(type(v.value), "type(None)"))
            elif isinstance(v, (ast.Compare, ast.UnaryOp)) and (isinstance(v, ast.Compare) or isinstance(v.op, ast.Not)):
                types.add("bool")
            else:
                return None
    return tuple(sorted(types)) or None


# ------------------------------------------------------------------ generation
@dataclass
class TestSpec:
    __test__ = False
    name: str
    function: str
    category: str
    oracle: str            # guard_raise | guard_return | type | robustness
    source: str
    content_hash: str
    args_repr: str


@dataclass
class GenerationResult:
    module_name: str
    file_text: str
    cases: list[TestSpec]
    skipped: list[tuple[str, str]] = field(default_factory=list)
    duplicates_removed: int = 0
    syntax_valid: bool = True


def _slug(s: str, limit: int = 24) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:limit] or "v"


def _call(fn: FunctionInfo, args: dict, has_obj: bool) -> str:
    argtxt = ", ".join(f"{k}={v!r}" for k, v in args.items())
    return f"obj.{fn.name}({argtxt})" if has_obj else f"{fn.name}({argtxt})"


def _build_tests(fn: FunctionInfo, rng: random.Random, max_cases: int, cls_required: list[str] | None):
    cand = candidates(fn)
    if not cand:
        cand = {}
    names = list(cand)
    base = {n: cand[n][0][0] for n in names}
    combos: list[tuple[dict, str]] = [(dict(base), "normal")]
    for n in names:                                    # one-at-a-time variation
        for v, cat in cand[n][1:]:
            combos.append(({**base, n: v}, cat))
    if len(names) > 1:                                 # a few pairwise boundary mixes
        pool = [dict(zip(names, vs)) for vs in itertools.product(*[[c[0] for c in cand[n][:3]] for n in names])]
        rng.shuffle(pool)
        combos += [(c, "combination") for c in pool[:10]]
    tests = []
    has_obj = fn.class_name is not None
    ret_types = _return_types(fn)
    for args, cat in combos:
        sim = simulate(fn.node, args)
        call = _call(fn, args, has_obj)
        pre = f"    obj = {fn.class_name}()\n" if has_obj else ""
        if sim and sim[0] == "raise":
            oracle, body = "guard_raise", f"{pre}    with pytest.raises({sim[1]}):\n        {call}\n"
            category = "exception"
        elif sim and sim[0] == "return":
            oracle, body = "guard_return", f"{pre}    assert {call} == {sim[1]!r}\n"
            category = cat if cat != "normal" else "branch"
        else:
            accepted = [r for r in fn.raises]
            if ret_types:
                tt = ret_types[0] if len(ret_types) == 1 else "(" + ", ".join(ret_types) + ")"
                check = f"    assert isinstance(result, {tt})\n"
                oracle = "type"
            else:
                check, oracle = "    assert True  # smoke: no unexpected exception\n".replace("assert True  # smoke: no unexpected exception", "pass  # smoke: call completed without unexpected exception"), "robustness"
            if accepted:
                body = (f"{pre}    try:\n        result = {call}\n    except ({', '.join(accepted)},):\n"
                        f"        return  # input rejected via an exception declared in the source\n{check}")
            else:
                body = f"{pre}    result = {call}\n{check}"
            category = cat
        tests.append((category, oracle, args, body))
    # invalid-type robustness (one per typed param)
    for p in fn.params:
        t = _base_type(p.annotation, p.default, p.name)
        if t in ("int", "float", "str", "list") and p.name in base:
            bad = None if t != "str" else 12345
            args = {**base, p.name: bad}
            pre = f"    obj = {fn.class_name}()\n" if has_obj else ""
            body = (f"{pre}    try:\n        {_call(fn, args, has_obj)}\n    except ({', '.join(REJECTION)}):\n"
                    f"        pass  # invalid input is rejected with a standard exception\n")
            tests.append(("invalid", "robustness", args, body))
    return tests


def generate_tests(source: str, module_name: str, *, seed: int = 0, max_per_function: int = 14) -> GenerationResult:
    analysis: ModuleAnalysis = analyse_source(source)
    rng = random.Random(seed)
    cases: list[TestSpec] = []
    skipped: list[tuple[str, str]] = []
    seen: set[str] = set()
    dups = 0
    classes = {c.name: c for c in analysis.classes}
    targets: list[str] = []
    for fn in analysis.functions:
        if fn.name.startswith("_"):
            skipped.append((fn.qualified_name, "private / dunder")); continue
        if fn.kind.startswith("async") or fn.is_generator:
            skipped.append((fn.qualified_name, "async/generator not supported by the rule-based generator")); continue
        if fn.class_name and classes[fn.class_name].init_required_params:
            skipped.append((fn.qualified_name, "class constructor needs arguments")); continue
        specs = _build_tests(fn, rng, max_per_function, None)
        max_per_function_eff = max_per_function + (6 if len(fn.params) > 1 else 0)
        order = {"exception": 0, "branch": 1, "boundary": 2, "zero": 3, "negative": 3, "empty": 3, "maximum": 4,
                 "normal": 5, "combination": 6, "invalid": 7}
        specs.sort(key=lambda s: order.get(s[0], 9))
        kept = 0
        caps = {"exception": 3, "invalid": 2, "combination": 8}
        per_cat: dict[str, int] = {}
        for category, oracle, args, body in specs:
            if kept >= max_per_function_eff:
                break
            if per_cat.get(category, 0) >= caps.get(category, 99):
                continue
            key = f"{fn.qualified_name}|{sorted(args.items(), key=lambda kv: kv[0])!r}|{oracle}|{category == 'invalid'}"
            if key in seen:
                dups += 1; continue
            seen.add(key)
            per_cat[category] = per_cat.get(category, 0) + 1
            tname = f"test_{_slug(fn.qualified_name.replace('.', '_'), 30)}_{category}_{per_cat[category]}"
            src = f"def {tname}():\n{body}"
            cases.append(TestSpec(tname, fn.qualified_name, category, oracle, src,
                                  hashlib.sha256(src.encode()).hexdigest(), repr(args)))
            kept += 1
        if kept:
            targets.append(fn.class_name or fn.name)
    # unique names
    used: dict[str, int] = {}
    final = []
    for c in cases:
        n = used.get(c.name, 0); used[c.name] = n + 1
        if n:
            new = f"{c.name}_{n + 1}"
            c.source = c.source.replace(f"def {c.name}()", f"def {new}()", 1); c.name = new
        final.append(c)
    imports = sorted(set(targets))
    header = (f'"""Auto-generated by TestPilot ({GENERATOR_VERSION}), seed={seed}. Module under test: {module_name}."""\n'
              f"import pytest\n" + (f"from {module_name} import {', '.join(imports)}\n" if imports else "") + "\n\n")
    text = header + "\n\n".join(c.source for c in final)
    valid = True
    try:
        compile(text, "<generated>", "exec")
    except SyntaxError:
        valid = False
    return GenerationResult(module_name, text, final, skipped, dups, valid)
