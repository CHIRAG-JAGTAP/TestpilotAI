"""Analyse Python source and generate pytest tests (offline, rule-based, no code is executed)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.engines.analyzer.analyzer import AnalysisError, analyse_source
from app.engines.generator.rule_based import generate_tests

router = APIRouter(prefix="/api", tags=["tests"])
MAX_SOURCE_CHARS = 200_000


class SourceIn(BaseModel):
    source: str = Field(min_length=1, max_length=MAX_SOURCE_CHARS)


class GenerateIn(SourceIn):
    module_name: str = Field(default="source", pattern=r"^[A-Za-z_][A-Za-z0-9_]*$", max_length=64)
    seed: int = 0
    max_per_function: int = Field(default=14, ge=1, le=50)


@router.post("/analyze")
def analyze(body: SourceIn) -> dict:
    try:
        return analyse_source(body.source).to_dict()
    except (AnalysisError, SyntaxError) as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/generate")
def generate(body: GenerateIn) -> dict:
    try:
        r = generate_tests(body.source, body.module_name, seed=body.seed, max_per_function=body.max_per_function)
    except (AnalysisError, SyntaxError) as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {
        "module_name": r.module_name,
        "file_text": r.file_text,
        "syntax_valid": r.syntax_valid,
        "duplicates_removed": r.duplicates_removed,
        "skipped": [{"function": f, "reason": why} for f, why in r.skipped],
        "cases": [{"name": c.name, "function": c.function, "category": c.category,
                   "oracle": c.oracle, "args": c.args_repr} for c in r.cases],
    }
