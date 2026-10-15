"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { Health, Rule, Run, RunResult, SuggestionResponse, TableDetail, TableSummary } from "@/lib/types";

const TYPE_LABELS: Record<string, string> = {
  expect_column_values_to_not_be_null: "Required value",
  expect_column_values_to_be_unique: "Unique value",
  expect_column_values_to_be_in_set: "Allowed values",
  expect_column_values_to_be_between: "Numeric range",
  expect_column_value_lengths_to_be_between: "Text length",
  expect_column_values_to_match_regex: "Pattern",
  expect_table_row_count_to_be_between: "Row count",
  expect_compound_columns_to_be_unique: "Unique combination",
};

type Draft = {
  title: string;
  plain_language: string;
  severity: string;
  column: string;
  min: string;
  max: string;
  values: string;
  regex: string;
  columnList: string;
};

function sourceLabel(generator: string) {
  if (generator === "llm") return "Suggested by the model";
  if (generator === "natural_language") return "From your description";
  return "Suggested from the data";
}

function formatValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "empty";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function formatWhen(value: string | null) {
  if (!value) return "";
  return new Date(value).toLocaleString();
}

function draftFromRule(rule: Rule): Draft {
  const kwargs = rule.kwargs || {};
  const values = Array.isArray(kwargs.value_set) ? kwargs.value_set.map(String).join(", ") : "";
  const columnList = Array.isArray(kwargs.column_list) ? kwargs.column_list.map(String).join(", ") : "";
  return {
    title: rule.title,
    plain_language: rule.plain_language,
    severity: rule.severity,
    column: String(kwargs.column || ""),
    min: kwargs.min_value === undefined || kwargs.min_value === null ? "" : String(kwargs.min_value),
    max: kwargs.max_value === undefined || kwargs.max_value === null ? "" : String(kwargs.max_value),
    values,
    regex: String(kwargs.regex || ""),
    columnList,
  };
}

function kwargsFromDraft(type: string, draft: Draft) {
  const kwargs: Record<string, unknown> = {};
  if (
    type !== "expect_table_row_count_to_be_between" &&
    type !== "expect_compound_columns_to_be_unique"
  ) {
    kwargs.column = draft.column;
  }
  if (
    type === "expect_column_values_to_be_between" ||
    type === "expect_column_value_lengths_to_be_between" ||
    type === "expect_table_row_count_to_be_between"
  ) {
    if (draft.min !== "") kwargs.min_value = Number(draft.min);
    if (draft.max !== "") kwargs.max_value = Number(draft.max);
  }
  if (type === "expect_column_values_to_be_in_set") {
    kwargs.value_set = draft.values
      .split(",")
      .map((part) => part.trim())
      .filter(Boolean)
      .map((part) => (/^-?\d+$/.test(part) ? Number(part) : part));
  }
  if (type === "expect_column_values_to_match_regex") kwargs.regex = draft.regex;
  if (type === "expect_compound_columns_to_be_unique") {
    kwargs.column_list = draft.columnList
      .split(",")
      .map((part) => part.trim())
      .filter(Boolean);
  }
  return kwargs;
}

export default function Assistant() {
  const [health, setHealth] = useState<Health | null>(null);
  const [tables, setTables] = useState<TableSummary[]>([]);
  const [selected, setSelected] = useState<TableSummary | null>(null);
  const [detail, setDetail] = useState<TableDetail | null>(null);
  const [rules, setRules] = useState<Rule[]>([]);
  const [history, setHistory] = useState<Run[]>([]);
  const [activeRun, setActiveRun] = useState<Run | null>(null);
  const [sentence, setSentence] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const requestToken = useRef(0);

  async function loadTable(table: TableSummary, token: number) {
    const query = new URLSearchParams({
      schema_name: table.schema_name,
      table_name: table.table_name,
    });
    const [nextDetail, loadedRules, nextRuns] = await Promise.all([
      api<TableDetail>(`/api/tables/${table.schema_name}/${table.table_name}`),
      api<Rule[]>(`/api/rules?${query}`),
      api<Run[]>(`/api/runs?${query}`),
    ]);
    if (token !== requestToken.current) return;
    let nextRules = loadedRules;
    if (nextRules.length === 0) {
      const suggestion = await api<SuggestionResponse>(
        `/api/tables/${table.schema_name}/${table.table_name}/suggestions`,
        { method: "POST" },
      );
      if (token !== requestToken.current) return;
      nextRules = await api<Rule[]>(`/api/rules?${query}`);
      if (suggestion.created.length > 0) {
        setNote(`Added ${suggestion.created.length} checks from this table. ${suggestion.note}`);
      }
    }
    setDetail(nextDetail);
    setRules(nextRules);
    setHistory(nextRuns);
    setActiveRun(nextRuns.find((run) => run.status === "completed") || null);
    setEditingId(null);
  }

  useEffect(() => {
    const token = ++requestToken.current;
    Promise.all([api<Health>("/api/health"), api<TableSummary[]>("/api/tables")])
      .then(async ([nextHealth, nextTables]) => {
        if (token !== requestToken.current) return;
        setHealth(nextHealth);
        setTables(nextTables);
        if (nextTables[0]) {
          setSelected(nextTables[0]);
          await loadTable(nextTables[0], token);
        }
      })
      .catch((reason: Error) => setError(reason.message || "The API is not running."));
  }, []);

  async function choose(table: TableSummary) {
    const token = ++requestToken.current;
    setSelected(table);
    setError("");
    setNote("");
    setBusy("Loading table");
    try {
      await loadTable(table, token);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load the table");
    } finally {
      if (token === requestToken.current) setBusy("");
    }
  }

  async function refreshRules() {
    if (!selected) return;
    const query = new URLSearchParams({
      schema_name: selected.schema_name,
      table_name: selected.table_name,
    });
    setRules(await api<Rule[]>(`/api/rules?${query}`));
  }

  async function suggest() {
    if (!selected) return;
    setBusy("Suggesting checks");
    setError("");
    try {
      const result = await api<{ note: string }>(
        `/api/tables/${selected.schema_name}/${selected.table_name}/suggestions`,
        { method: "POST" },
      );
      setNote(result.note);
      await refreshRules();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not suggest checks");
    } finally {
      setBusy("");
    }
  }

  async function addSentence(event: FormEvent) {
    event.preventDefault();
    if (!selected || !sentence.trim()) return;
    setBusy("Saving check");
    setError("");
    try {
      const result = await api<{ note: string }>("/api/rules/natural-language", {
        method: "POST",
        body: JSON.stringify({
          schema_name: selected.schema_name,
          table_name: selected.table_name,
          text: sentence,
        }),
      });
      setNote(result.note);
      setSentence("");
      await refreshRules();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save that check");
    } finally {
      setBusy("");
    }
  }

  async function runChecks() {
    if (!selected) return;
    setBusy("Running checks");
    setError("");
    try {
      const run = await api<Run>("/api/runs", {
        method: "POST",
        body: JSON.stringify({
          schema_name: selected.schema_name,
          table_name: selected.table_name,
        }),
      });
      setActiveRun(run);
      const query = new URLSearchParams({
        schema_name: selected.schema_name,
        table_name: selected.table_name,
      });
      setHistory(await api<Run[]>(`/api/runs?${query}`));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The checks could not be run");
    } finally {
      setBusy("");
    }
  }

  async function toggle(rule: Rule) {
    setError("");
    try {
      const updated = await api<Rule>(`/api/rules/${rule.id}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled: !rule.enabled }),
      });
      setRules((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not update the check");
    }
  }

  async function remove(rule: Rule) {
    if (!window.confirm(`Remove “${rule.title}”?`)) return;
    setError("");
    try {
      await api(`/api/rules/${rule.id}`, { method: "DELETE" });
      setRules((current) => current.filter((item) => item.id !== rule.id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not remove the check");
    }
  }

  async function saveEdit(rule: Rule) {
    if (!draft) return;
    setBusy("Saving check");
    setError("");
    try {
      const updated = await api<Rule>(`/api/rules/${rule.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          title: draft.title,
          plain_language: draft.plain_language,
          severity: draft.severity,
          kwargs: kwargsFromDraft(rule.expectation_type, draft),
        }),
      });
      setRules((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setEditingId(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save the check");
    } finally {
      setBusy("");
    }
  }

  const resultsByRule = new Map<string, RunResult>();
  activeRun?.results.forEach((result) => {
    if (result.rule_id) resultsByRule.set(result.rule_id, result);
  });
  const sampleColumns = detail?.sample_rows[0] ? Object.keys(detail.sample_rows[0]) : [];

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <p className="eyebrow">PostgreSQL · Great Expectations</p>
          <h1>Data Quality Assistant</h1>
          <p className="lede">
            Review a table, keep the checks that matter, and describe new ones in everyday language.
          </p>
        </div>
        <div className="status-pill">
          {health
            ? health.llm_configured
              ? `Model: ${health.llm_provider} · ${health.llm_model}`
              : "Model: profiler until a free Gemini key is added"
            : "Connecting…"}
        </div>
      </header>
      <div className="layout">
        <aside className="sidebar">
          <h2>Tables</h2>
          {tables.length === 0 && <p className="muted">No tables yet.</p>}
          {tables.map((table) => (
            <button
              key={`${table.schema_name}.${table.table_name}`}
              className={
                selected?.schema_name === table.schema_name && selected.table_name === table.table_name
                  ? "table-button active"
                  : "table-button"
              }
              onClick={() => choose(table)}
              type="button"
            >
              <strong>
                {table.schema_name}.{table.table_name}
              </strong>
              <span>{table.row_count} rows</span>
            </button>
          ))}
        </aside>
        <main className="main">
          {!selected && <div className="empty">Choose a table to review its shape and checks.</div>}
          {selected && (
            <div className="stack">
              {error && <div className="banner error">{error}</div>}
              {note && <div className="banner">{note}</div>}
              {health && !health.llm_configured && (
                <div className="banner">{health.message}</div>
              )}
              <section className="card">
                <div className="card-head">
                  <div>
                    <h2>
                      {selected.schema_name}.{selected.table_name}
                    </h2>
                    <p className="muted">{detail ? `${detail.row_count} rows` : "Loading…"}</p>
                  </div>
                  <div className="actions">
                    <button className="btn" type="button" onClick={suggest} disabled={!!busy}>
                      Suggest checks
                    </button>
                    <button className="btn primary" type="button" onClick={runChecks} disabled={!!busy || rules.every((rule) => !rule.enabled)}>
                      {busy === "Running checks" ? "Running…" : "Run checks"}
                    </button>
                  </div>
                </div>
                {detail && detail.highlights.length > 0 && (
                  <ul className="highlights">
                    {detail.highlights.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                )}
                {detail && (
                  <div className="scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Column</th>
                          <th>Type</th>
                          <th>Empty</th>
                          <th>Distinct</th>
                          <th>Min</th>
                          <th>Max</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detail.columns.map((column) => (
                          <tr key={column.name}>
                            <td>{column.name}</td>
                            <td>{column.data_type}</td>
                            <td>{column.null_count === 0 ? "none" : `${column.null_percent}%`}</td>
                            <td>{column.distinct_count}</td>
                            <td>{formatValue(column.min_value)}</td>
                            <td>{formatValue(column.max_value)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                {detail && detail.sample_rows.length > 0 && (
                  <div className="scroll">
                    <table>
                      <thead>
                        <tr>
                          {sampleColumns.map((column) => (
                            <th key={column}>{column}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {detail.sample_rows.map((row, index) => (
                          <tr key={index}>
                            {sampleColumns.map((column) => (
                              <td key={column}>{formatValue(row[column])}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>

              <section className="card">
                <h2>Quality report</h2>
                {!activeRun && <p className="muted">Run the checks once. The report stays here until you run them again.</p>}
                {activeRun && (
                  <>
                    <div className="summary-counts">
                      <span className="pass-count">{activeRun.passed_count} passed</span>
                      <span className="fail-count">{activeRun.failed_count} failed</span>
                      <span className="warn-count">{activeRun.warning_count} warnings</span>
                      {activeRun.error_count > 0 && <span className="fail-count">{activeRun.error_count} errors</span>}
                    </div>
                    <p className="muted">Saved {formatWhen(activeRun.finished_at)}. Opening this table again shows this report without re-running.</p>
                    <ul className="report">
                      {activeRun.results
                        .filter((result) => result.outcome !== "passed")
                        .map((result) => (
                          <li key={result.id}>
                            <strong>{result.title}</strong> · {result.outcome}
                            {result.sample_failures.length > 0 && (
                              <> — {result.sample_failures.slice(0, 3).map(formatValue).join(", ")}</>
                            )}
                            {result.error_message ? ` — ${result.error_message}` : ""}
                          </li>
                        ))}
                    </ul>
                  </>
                )}
                {history.length > 1 && (
                  <div className="history">
                    {history.map((run) => (
                      <button
                        key={run.id}
                        type="button"
                        className={activeRun?.id === run.id ? "history-button active" : "history-button"}
                        onClick={() => setActiveRun(run)}
                      >
                        {formatWhen(run.started_at)} · {run.failed_count} failed
                      </button>
                    ))}
                  </div>
                )}
              </section>

              <section className="stack">
                <div className="card-head">
                  <h2>Checks</h2>
                  <span className="muted">{busy}</span>
                </div>
                {rules.length === 0 && (
                  <div className="card empty">Suggest checks, or describe one below.</div>
                )}
                {rules.map((rule) => {
                  const result = resultsByRule.get(rule.id);
                  const stale =
                    result && activeRun?.finished_at
                      ? new Date(rule.updated_at).getTime() > new Date(activeRun.finished_at).getTime()
                      : false;
                  const outcome = result?.outcome;
                  return (
                    <article
                      key={rule.id}
                      className={`card rule ${rule.enabled ? outcome || "" : "paused"}`}
                    >
                      <div className="card-head">
                        <h3>{rule.title}</h3>
                        <div className="chips">
                          <span className={`chip ${rule.severity}`}>{rule.severity}</span>
                          {outcome && <span className={`chip ${outcome}`}>{outcome}</span>}
                          {!rule.enabled && <span className="chip">paused</span>}
                        </div>
                      </div>
                      <p className="plain">{rule.plain_language}</p>
                      <p className="muted">
                        {TYPE_LABELS[rule.expectation_type] || rule.expectation_type} · {sourceLabel(rule.generator)}
                        {stale ? " · edited since the last run" : ""}
                      </p>
                      {result?.error_message && <p className="banner error">{result.error_message}</p>}
                      {result && result.sample_failures.length > 0 && (
                        <p className="samples">
                          Examples:{" "}
                          {result.sample_failures.map((value, index) => (
                            <strong key={index}>{formatValue(value)} </strong>
                          ))}
                          {result.unexpected_count !== null && (
                            <span>
                              ({result.unexpected_count} unexpected
                              {result.unexpected_percent !== null
                                ? `, ${result.unexpected_percent.toFixed(1)}%`
                                : ""}
                              )
                            </span>
                          )}
                        </p>
                      )}
                      <details>
                        <summary>Great Expectations configuration</summary>
                        <pre>
                          {JSON.stringify(
                            { expectation_type: rule.expectation_type, kwargs: rule.kwargs },
                            null,
                            2,
                          )}
                        </pre>
                      </details>
                      {editingId === rule.id && draft && detail && (
                        <div className="form">
                          <label>
                            Title
                            <input
                              value={draft.title}
                              onChange={(event) => setDraft({ ...draft, title: event.target.value })}
                            />
                          </label>
                          <label>
                            What this check means
                            <textarea
                              value={draft.plain_language}
                              onChange={(event) =>
                                setDraft({ ...draft, plain_language: event.target.value })
                              }
                            />
                          </label>
                          <label>
                            If it fails
                            <select
                              value={draft.severity}
                              onChange={(event) => setDraft({ ...draft, severity: event.target.value })}
                            >
                              <option value="critical">Critical failure</option>
                              <option value="warning">Warning</option>
                            </select>
                          </label>
                          {rule.expectation_type !== "expect_table_row_count_to_be_between" &&
                            rule.expectation_type !== "expect_compound_columns_to_be_unique" && (
                              <label>
                                Column
                                <select
                                  value={draft.column}
                                  onChange={(event) => setDraft({ ...draft, column: event.target.value })}
                                >
                                  {detail.columns.map((column) => (
                                    <option key={column.name} value={column.name}>
                                      {column.name}
                                    </option>
                                  ))}
                                </select>
                              </label>
                            )}
                          {(rule.expectation_type.includes("between") ||
                            rule.expectation_type === "expect_table_row_count_to_be_between") && (
                            <div className="row">
                              <label>
                                Minimum
                                <input
                                  value={draft.min}
                                  onChange={(event) => setDraft({ ...draft, min: event.target.value })}
                                />
                              </label>
                              <label>
                                Maximum
                                <input
                                  value={draft.max}
                                  onChange={(event) => setDraft({ ...draft, max: event.target.value })}
                                />
                              </label>
                            </div>
                          )}
                          {rule.expectation_type === "expect_column_values_to_be_in_set" && (
                            <label>
                              Allowed values, separated by commas
                              <textarea
                                value={draft.values}
                                onChange={(event) => setDraft({ ...draft, values: event.target.value })}
                              />
                            </label>
                          )}
                          {rule.expectation_type === "expect_column_values_to_match_regex" && (
                            <label>
                              Pattern
                              <input
                                value={draft.regex}
                                onChange={(event) => setDraft({ ...draft, regex: event.target.value })}
                              />
                            </label>
                          )}
                          {rule.expectation_type === "expect_compound_columns_to_be_unique" && (
                            <label>
                              Columns, separated by commas
                              <input
                                value={draft.columnList}
                                onChange={(event) =>
                                  setDraft({ ...draft, columnList: event.target.value })
                                }
                              />
                            </label>
                          )}
                          <div className="actions">
                            <button className="btn primary" type="button" onClick={() => saveEdit(rule)}>
                              Save changes
                            </button>
                            <button className="btn" type="button" onClick={() => setEditingId(null)}>
                              Cancel
                            </button>
                          </div>
                        </div>
                      )}
                      {editingId !== rule.id && (
                        <div className="actions">
                          <button
                            className="btn"
                            type="button"
                            onClick={() => {
                              setEditingId(rule.id);
                              setDraft(draftFromRule(rule));
                            }}
                          >
                            Edit
                          </button>
                          <button className="btn" type="button" onClick={() => toggle(rule)}>
                            {rule.enabled ? "Pause" : "Use this check"}
                          </button>
                          <button className="btn danger" type="button" onClick={() => remove(rule)}>
                            Remove
                          </button>
                        </div>
                      )}
                    </article>
                  );
                })}
              </section>

              <form className="card composer" onSubmit={addSentence}>
                <h2>Describe a check</h2>
                <p className="muted">
                  Example: email is required. Amount should be between 0 and 1000. Status should be one of
                  paid, pending, shipped, cancelled.
                </p>
                <textarea
                  value={sentence}
                  onChange={(event) => setSentence(event.target.value)}
                  placeholder="Write the rule the way you would say it to a teammate"
                />
                <div className="actions">
                  <button className="btn primary" type="submit" disabled={!!busy || sentence.trim().length < 3}>
                    Add this check
                  </button>
                </div>
              </form>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
