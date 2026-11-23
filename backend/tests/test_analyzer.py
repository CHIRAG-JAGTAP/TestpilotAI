from pathlib import Path

import pytest

from app.engines.analyzer.analyzer import AnalysisError, analyse_source, untested_functions

BENCH = Path(__file__).resolve().parents[2] / "benchmarks" / "b01_arithmetic" / "source.py"


def info(name):
    a = analyse_source(BENCH.read_text())
    return next(f for f in a.functions if f.qualified_name == name)


def test_counts_and_module_metrics():
    a = analyse_source(BENCH.read_text())
    assert a.function_count == 7 and a.class_count == 1
    assert a.complexity == sum(f.complexity for f in a.functions)
    assert a.source_lines <= a.total_lines


@pytest.mark.parametrize("name,complexity,branches", [
    ("is_even", 1, 0), ("safe_divide", 2, 2), ("sign", 3, 4), ("clamp", 4, 6),
    ("grade", 6, 8),           # 4 decisions + one `or` + 1
])
def test_cyclomatic_complexity_matches_hand_calculation(name, complexity, branches):
    f = info(name)
    assert (f.complexity, f.branch_count) == (complexity, branches)


def test_elif_is_distinguished_and_raises_collected():
    assert [c.kind for c in info("sign").conditions] == ["if", "elif"]
    assert info("grade").raises == ["ValueError"] and info("safe_divide").raises == ["ZeroDivisionError"]


def test_params_annotations_and_methods():
    f = info("Counter.add")
    assert f.kind == "method" and f.class_name == "Counter"
    assert [(p.name, p.annotation) for p in f.params] == [("self", None), ("amount", "int")]
    assert any("zero" in e or "negative" in e for e in info("clamp").edge_cases)


def test_nested_function_not_counted_in_outer_complexity():
    a = analyse_source("def outer(x):\n    def inner(y):\n        if y:\n            return 1\n    return x\n")
    assert a.functions[0].complexity == 1


def test_malformed_source_raises_analysis_error():
    with pytest.raises(AnalysisError):
        analyse_source("def broken(:\n    pass")


def test_untested_function_detection():
    a = analyse_source(BENCH.read_text())
    missing = untested_functions(a, ["def test_a():\n    clamp(1, 0, 2)\n    Counter().add(1)\n"])
    assert "clamp" not in missing and "Counter.add" not in missing and "sign" in missing
