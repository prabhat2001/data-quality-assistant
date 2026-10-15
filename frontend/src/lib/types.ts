export type Health = {
  status: string;
  database: string;
  llm_provider: string;
  llm_model: string;
  llm_configured: boolean;
  suggestion_mode: string;
  message: string;
};

export type TableSummary = {
  schema_name: string;
  table_name: string;
  row_count: number;
};

export type Column = {
  name: string;
  data_type: string;
  nullable: boolean;
  null_count: number;
  null_percent: number;
  distinct_count: number;
  min_value?: string | number | null;
  max_value?: string | number | null;
};

export type TableDetail = TableSummary & {
  columns: Column[];
  sample_rows: Record<string, unknown>[];
  highlights: string[];
};

export type Rule = {
  id: string;
  schema_name: string;
  table_name: string;
  title: string;
  plain_language: string;
  expectation_type: string;
  kwargs: Record<string, unknown>;
  severity: string;
  enabled: boolean;
  generator: string;
  created_at: string;
  updated_at: string;
};

export type RunResult = {
  id: string;
  rule_id: string | null;
  title: string;
  expectation_type: string;
  kwargs: Record<string, unknown>;
  severity: string;
  outcome: string;
  unexpected_count: number | null;
  unexpected_percent: number | null;
  sample_failures: unknown[];
  observed: Record<string, unknown>;
  error_message: string | null;
};

export type Run = {
  id: string;
  schema_name: string;
  table_name: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  passed_count: number;
  failed_count: number;
  warning_count: number;
  error_count: number;
  error_message: string | null;
  results: RunResult[];
};

export type SuggestionResponse = {
  generator: string;
  provider: string | null;
  model: string | null;
  note: string;
  created: Rule[];
};

export type LanguageResponse = {
  rules: Rule[];
  translated_by: string;
  note: string;
};
