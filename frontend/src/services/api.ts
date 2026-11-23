import type { AnalysisResult, DbHealth, GenerateResult } from "../types/api";

async function call<T>(url: string, body?: unknown): Promise<T> {
  const res = await fetch(url, body === undefined ? undefined : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try { const d = await res.json(); if (typeof d.detail === "string") msg = d.detail; } catch { /* ignore */ }
    throw new Error(msg);
  }
  return res.json() as Promise<T>;
}

export const analyze = (source: string) => call<AnalysisResult>("/api/analyze", { source });
export const generate = (source: string, module_name: string) =>
  call<GenerateResult>("/api/generate", { source, module_name });
export const dbHealth = () => call<DbHealth>("/api/health/database");
