"use client";

import { useEffect, useState } from "react";

interface JsonEditorProps {
  label: string;
  value: unknown;
  onSave?: (value: Record<string, unknown>) => void;
  onChange?: (value: string) => void;
  disabled?: boolean;
  errorMessage?: string | null;
}

function stringifyJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

export function JsonEditor({
  label,
  value,
  onSave,
  onChange,
  disabled = false,
  errorMessage = null,
}: JsonEditorProps) {
  const [text, setText] = useState(() => stringifyJson(value));
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setText(stringifyJson(value));
    setError(null);
  }, [value]);

  function handleChange(nextValue: string): void {
    setText(nextValue);
    setError(null);
    onChange?.(nextValue);
  }

  function handleSave(): void {
    try {
      const parsed = JSON.parse(text) as Record<string, unknown>;
      setError(null);
      onSave?.(parsed);
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "Unknown parse error";
      setError(`${label} JSON is invalid: ${message}`);
    }
  }

  return (
    <section className="card">
      <div className="section-header">
        <h2>{label}</h2>
        {onSave ? (
          <button type="button" onClick={handleSave} disabled={disabled}>
            {`Save ${label}`}
          </button>
        ) : null}
      </div>
      <label className="field">
        <span>{label} JSON</span>
        <textarea
          aria-label={`${label} JSON`}
          className="json-editor"
          value={text}
          onChange={(event) => handleChange(event.target.value)}
          spellCheck={false}
          disabled={disabled}
          rows={16}
        />
      </label>
      {error || errorMessage ? <p className="error-text">{error ?? errorMessage}</p> : null}
    </section>
  );
}
