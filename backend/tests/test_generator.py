import ast
import sys
import types
from collections import Counter
from pathlib import Path

import pytest

from app.engines.generator.rule_based import generate_tests, safe_eval, simulate

SRC = (Path(__file__).resolve().parents[2] / "benchmarks" / "b01_arithmetic" / "source.py").read_text()


def run_generated(result, module_source):
    """Execute generated tests in-process against `module_source`; return names of failing tests."""
    mod = types.ModuleType(result.module_name)
    exec(compile(module_source, "<src>", "exec"), mod.__dict__)
    sys.modules[result.module_name] = mod
    ns: dict = {}
    exec(compile(result.file_text, "<generated>", "exec"), ns)
    failed = []
    for case in result.cases:
        try:
            ns[case.name]()
        except BaseException:
            failed.append(case.name)
    return failed


def test_generated_file_is_valid_python_and_has_unique_names():
    r = generate_tests(SRC, "source")
    ast.parse(r.file_text)
    assert r.syntax_valid and len(r.cases) > 30
    names = [c.name for c in r.cases]
    assert len(names) == len(set(names))
    assert len({c.content_hash for c in r.cases}) == len(r.cases)       # no duplicate bodies


def test_generation_is_deterministic():
    assert generate_tests(SRC, "source", seed=7).file_text == generate_tests(SRC, "source", seed=7).file_text


def test_generated_tests_pass_on_the_correct_source():
    assert run_generated(generate_tests(SRC, "source"), SRC) == []


def test_covers_required_scenario_categories():
    cats = Counter(c.category for c in generate_tests(SRC, "source").cases)
    for needed in ("exception", "boundary", "zero", "negative", "maximum", "invalid", "branch"):
        assert cats[needed] > 0, needed


def test_no_tautological_assertions():
    """Oracles come from the source's guards / types - never from a recorded return value."""
    r = generate_tests(SRC, "source")
    assert {c.oracle for c in r.cases} <= {"guard_raise", "guard_return", "type", "robustness"}
    assert "assert True" not in r.file_text


@pytest.mark.parametrize("old,new", [
    ("if value < low:\n        return low", "if value < low:\n        return high"),
    ("if value > high:\n        return high", "if value > high:\n        return low"),
    ("if n < 0:", "if n <= 0:"),
    ("score >= 90", "score >= 91"),
    ("score > 100", "score > 101"),
    ("if amount < 0:", "if amount < -5:"),
    ("n % 2 == 0", "n % 2 == 1"),
])
def test_generated_tests_detect_seeded_bugs(old, new):
    assert old in SRC
    assert len(run_generated(generate_tests(SRC, "source"), SRC.replace(old, new))) >= 1


def test_equivalent_mutant_survives():
    """`a / 0` raises ZeroDivisionError anyway, so this mutant is behaviourally equivalent (documented limitation)."""
    assert run_generated(generate_tests(SRC, "source"), SRC.replace("if b == 0:", "if b == 99999:")) == []


def test_methods_use_instance_not_self_argument():
    r = generate_tests(SRC, "source")
    add = [c for c in r.cases if c.function == "Counter.add"]
    assert add and all("obj = Counter()" in c.source and "self" not in c.args_repr for c in add)


def test_unsupported_targets_are_reported_not_silently_dropped():
    r = generate_tests("def _hidden(x):\n    return x\n\nasync def a(x):\n    return x\n\nclass K:\n    def __init__(self, v):\n        self.v = v\n    def m(self):\n        return 1\n", "m")
    reasons = dict(r.skipped)
    assert reasons["_hidden"] and reasons["a"] and reasons["K.m"] and r.cases == []


def test_safe_eval_refuses_calls_and_unknown_names():
    assert safe_eval(ast.parse("x > 1", mode="eval").body, {"x": 2}) == (True, True)
    assert safe_eval(ast.parse("__import__('os').system('x')", mode="eval").body, {"x": 1})[0] is False
    assert safe_eval(ast.parse("y > 1", mode="eval").body, {"x": 1})[0] is False


def test_simulate_guard_chain():
    fn = ast.parse("def f(n):\n    if n < 0:\n        raise ValueError('x')\n    elif n == 0:\n        return 0\n    return n * 2\n").body[0]
    assert simulate(fn, {"n": -1}) == ("raise", "ValueError")
    assert simulate(fn, {"n": 0}) == ("return", 0)
    assert simulate(fn, {"n": 3}) == ("return", 6)
