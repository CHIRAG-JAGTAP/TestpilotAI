import { useState } from "react";
import { analyze, generate } from "../services/api";
import type { AnalysisResult, GenerateResult } from "../types/api";

const SAMPLE = `def clamp(value: int, low: int, high: int) -> int:
    if low > high:
        raise ValueError("low must not exceed high")
    if value < low:
        return low
    if value > high:
        return high
    return value


def sign(n: int) -> int:
    if n < 0:
        return -1
    elif n == 0:
        return 0
    return 1
`;

export default function Generator() {
  const [source, setSource] = useState(SAMPLE);
  const [moduleName, setModuleName] = useState("source");
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null);
  const [result, setResult] = useState<GenerateResult | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function run() {
    setBusy(true); setError(""); setResult(null); setAnalysis(null);
    try {
      const [a, g] = await Promise.all([analyze(source), generate(source, moduleName)]);
      setAnalysis(a); setResult(g);
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  function download() {
    if (!result) return;
    const url = URL.createObjectURL(new Blob([result.file_text], { type: "text/x-python" }));
    const a = document.createElement("a");
    a.href = url; a.download = `test_${result.module_name}.py`; a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="grid">
      <section className="card">
        <h2>1. Paste your Python code</h2>
        <label>Module name (the file name without .py)
          <input value={moduleName} onChange={e => setModuleName(e.target.value)} />
        </label>
        <textarea value={source} onChange={e => setSource(e.target.value)} spellCheck={false} rows={22} />
        <button onClick={run} disabled={busy || !source.trim()}>{busy ? "Working…" : "Analyze & generate tests"}</button>
        {error && <p className="error">{error}</p>}
      </section>

      <section className="card">
        <h2>2. Results</h2>
        {!result && !error && <p className="muted">Generated tests will appear here.</p>}
        {analysis && (
          <ul className="stats">
            <li><b>{analysis.function_count}</b> functions</li>
            <li><b>{analysis.class_count}</b> classes</li>
            <li><b>{analysis.branch_count}</b> branches</li>
            <li><b>{analysis.complexity}</b> complexity</li>
          </ul>
        )}
        {result && (
          <>
            <p>{result.cases.length} tests generated {result.syntax_valid ? "(valid Python)" : "(SYNTAX PROBLEM)"}.
              Save as <code>test_{result.module_name}.py</code> next to <code>{result.module_name}.py</code> and run <code>pytest</code>.</p>
            <button onClick={download}>Download test file</button>
            <button className="secondary" onClick={() => navigator.clipboard?.writeText(result.file_text)}>Copy</button>
            <pre>{result.file_text}</pre>
            {result.skipped.length > 0 && (
              <details><summary>{result.skipped.length} skipped</summary>
                <ul>{result.skipped.map(s => <li key={s.function}><code>{s.function}</code>: {s.reason}</li>)}</ul>
              </details>
            )}
          </>
        )}
      </section>
    </div>
  );
}
