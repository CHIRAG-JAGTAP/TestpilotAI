from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

SRC = (Path(__file__).resolve().parents[2] / "benchmarks" / "b01_arithmetic" / "source.py").read_text()


def test_analyze_and_generate_endpoints():
    c = TestClient(app)
    a = c.post("/api/analyze", json={"source": SRC})
    assert a.status_code == 200 and a.json()["function_count"] >= 2
    g = c.post("/api/generate", json={"source": SRC, "module_name": "source"})
    assert g.status_code == 200
    body = g.json()
    assert body["syntax_valid"] and len(body["cases"]) > 0 and "def test_" in body["file_text"]


def test_bad_input_is_rejected():
    c = TestClient(app)
    assert c.post("/api/analyze", json={"source": "def (:"}).status_code == 422
    assert c.post("/api/generate", json={"source": "x=1", "module_name": "bad name"}).status_code == 422
