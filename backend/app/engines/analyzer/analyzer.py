"""AST-based source analyser (Phase 3). Pure stdlib; never executes the analysed code."""
from __future__ import annotations

import ast
from dataclasses import asdict, dataclass, field

DECISIONS = (ast.If, ast.While, ast.For, ast.AsyncFor, ast.IfExp)
SKIP_DESCENT = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)


class AnalysisError(ValueError):
    """Source could not be parsed."""


@dataclass
class ParamInfo:
    name: str
    annotation: str | None
    default: str | None
    kind: str            # positional | vararg | kwonly | kwarg


@dataclass
class ConditionInfo:
    lineno: int
    kind: str            # if | elif | while | for | ifexp | boolop | except
    text: str


@dataclass
class FunctionInfo:
    name: str
    qualified_name: str
    class_name: str | None
    kind: str            # function | async_function | method | async_method
    lineno: int
    end_lineno: int
    params: list[ParamInfo]
    returns: str | None
    complexity: int = 1
    branch_count: int = 0          # 2 outcomes per decision point (true/false)
    conditions: list[ConditionInfo] = field(default_factory=list)
    raises: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    has_loops: bool = False
    has_try: bool = False
    is_generator: bool = False
    edge_cases: list[str] = field(default_factory=list)
    node: ast.AST | None = field(default=None, repr=False, compare=False)


@dataclass
class ClassInfo:
    name: str
    lineno: int
    bases: list[str]
    methods: list[str]
    init_required_params: list[str]


@dataclass
class ModuleAnalysis:
    functions: list[FunctionInfo]
    classes: list[ClassInfo]
    imports: list[str]
    total_lines: int
    source_lines: int
    function_count: int
    class_count: int
    branch_count: int
    complexity: int

    def to_dict(self) -> dict:
        d = asdict(self)
        for f in d["functions"]:
            f.pop("node", None)
        return d


def _walk(node: ast.AST):
    """Like ast.walk but does not descend into nested defs/lambdas/classes."""
    for child in ast.iter_child_nodes(node):
        yield child
        if not isinstance(child, SKIP_DESCENT):
            yield from _walk(child)


def _u(n: ast.AST | None) -> str | None:
    return ast.unparse(n) if n is not None else None


def _params(args: ast.arguments) -> list[ParamInfo]:
    out: list[ParamInfo] = []
    pos = args.posonlyargs + args.args
    defaults = [None] * (len(pos) - len(args.defaults)) + list(args.defaults)
    for a, d in zip(pos, defaults):
        out.append(ParamInfo(a.arg, _u(a.annotation), _u(d), "positional"))
    if args.vararg:
        out.append(ParamInfo(args.vararg.arg, _u(args.vararg.annotation), None, "vararg"))
    for a, d in zip(args.kwonlyargs, args.kw_defaults):
        out.append(ParamInfo(a.arg, _u(a.annotation), _u(d), "kwonly"))
    if args.kwarg:
        out.append(ParamInfo(args.kwarg.arg, _u(args.kwarg.annotation), None, "kwarg"))
    return out


def _analyse_function(fn: ast.FunctionDef | ast.AsyncFunctionDef, cls: str | None) -> FunctionInfo:
    is_async = isinstance(fn, ast.AsyncFunctionDef)
    info = FunctionInfo(
        name=fn.name, qualified_name=f"{cls}.{fn.name}" if cls else fn.name, class_name=cls,
        kind=("async_" if is_async else "") + ("method" if cls else "function"),
        lineno=fn.lineno, end_lineno=fn.end_lineno or fn.lineno,
        params=_params(fn.args), returns=_u(fn.returns), node=fn)
    elif_ids = {id(n.orelse[0]) for n in _walk(fn)
                if isinstance(n, ast.If) and len(n.orelse) == 1 and isinstance(n.orelse[0], ast.If)}
    complexity, decisions = 1, 0
    for n in _walk(fn):
        if isinstance(n, ast.If):
            kind = "elif" if id(n) in elif_ids else "if"
            info.conditions.append(ConditionInfo(n.lineno, kind, _u(n.test)))
            complexity += 1; decisions += 1
        elif isinstance(n, ast.While):
            info.conditions.append(ConditionInfo(n.lineno, "while", _u(n.test)))
            complexity += 1; decisions += 1; info.has_loops = True
        elif isinstance(n, (ast.For, ast.AsyncFor)):
            info.conditions.append(ConditionInfo(n.lineno, "for", f"{_u(n.target)} in {_u(n.iter)}"))
            complexity += 1; decisions += 1; info.has_loops = True
        elif isinstance(n, ast.IfExp):
            info.conditions.append(ConditionInfo(n.lineno, "ifexp", _u(n.test)))
            complexity += 1; decisions += 1
        elif isinstance(n, ast.BoolOp):
            complexity += len(n.values) - 1
        elif isinstance(n, ast.ExceptHandler):
            info.conditions.append(ConditionInfo(n.lineno, "except", _u(n.type) or "BaseException"))
            complexity += 1
        elif isinstance(n, ast.comprehension):
            complexity += 1 + len(n.ifs)
        elif isinstance(n, ast.Try):
            info.has_try = True
        elif isinstance(n, ast.Raise) and n.exc is not None:
            exc = n.exc.func if isinstance(n.exc, ast.Call) else n.exc
            name = _u(exc)
            if name and name not in info.raises:
                info.raises.append(name)
        elif isinstance(n, ast.Call):
            name = _u(n.func)
            if name and name not in info.calls:
                info.calls.append(name)
        elif isinstance(n, (ast.Yield, ast.YieldFrom)):
            info.is_generator = True
    info.complexity, info.branch_count = complexity, decisions * 2
    info.edge_cases = _edge_cases(info)
    return info


def _edge_cases(f: FunctionInfo) -> list[str]:
    out = []
    for p in f.params:
        t = (p.annotation or "").replace(" ", "")
        if t in ("int", "float"):
            out.append(f"{p.name}: zero, negative and boundary values")
        elif t == "str":
            out.append(f"{p.name}: empty string")
        elif t.startswith(("list", "List", "dict", "Dict", "tuple", "set")):
            out.append(f"{p.name}: empty collection")
        if "Optional" in t or "None" in t:
            out.append(f"{p.name}: None")
    if "ZeroDivisionError" in f.raises or any(isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Div, ast.FloorDiv, ast.Mod))
                                              for n in _walk(f.node)):
        out.append("division: zero divisor")
    for r in f.raises:
        out.append(f"raises {r}")
    if f.has_loops:
        out.append("loop: zero and one iteration")
    return list(dict.fromkeys(out))


def analyse_source(source: str) -> ModuleAnalysis:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise AnalysisError(f"line {exc.lineno}: {exc.msg}") from exc
    funcs: list[FunctionInfo] = []
    classes: list[ClassInfo] = []
    imports: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs.append(_analyse_function(node, None))
        elif isinstance(node, ast.ClassDef):
            methods, required = [], []
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    funcs.append(_analyse_function(item, node.name)); methods.append(item.name)
                    if item.name == "__init__":
                        ps = _params(item.args)[1:]
                        required = [p.name for p in ps if p.kind == "positional" and p.default is None]
            classes.append(ClassInfo(node.name, node.lineno, [ast.unparse(b) for b in node.bases], methods, required))
        elif isinstance(node, ast.Import):
            imports += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or ".")
    lines = source.splitlines()
    return ModuleAnalysis(
        functions=funcs, classes=classes, imports=imports, total_lines=len(lines),
        source_lines=sum(1 for l in lines if l.strip() and not l.strip().startswith("#")),
        function_count=len(funcs), class_count=len(classes),
        branch_count=sum(f.branch_count for f in funcs), complexity=sum(f.complexity for f in funcs))


def untested_functions(analysis: ModuleAnalysis, test_sources: list[str]) -> list[str]:
    """Functions never called (by name) in any of the given test sources."""
    called: set[str] = set()
    for src in test_sources:
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for n in ast.walk(tree):
            if isinstance(n, ast.Call):
                if isinstance(n.func, ast.Name):
                    called.add(n.func.id)
                elif isinstance(n.func, ast.Attribute):
                    called.add(n.func.attr)
    return [f.qualified_name for f in analysis.functions if f.name not in called]
