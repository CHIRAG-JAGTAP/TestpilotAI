export interface GeneratedCase { name: string; function: string; category: string; oracle: string; args: string }
export interface GenerateResult {
  module_name: string; file_text: string; syntax_valid: boolean; duplicates_removed: number;
  skipped: { function: string; reason: string }[]; cases: GeneratedCase[];
}
export interface AnalysisResult {
  function_count: number; class_count: number; branch_count: number; complexity: number;
  total_lines: number; source_lines: number; imports: string[];
  functions: { qualified_name: string; name: string }[];
}
export interface DbHealth { connected: boolean; journal_mode: string; integrity: { ok: boolean }; file_size_bytes: number }
