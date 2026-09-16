"use client";

import { useEffect, useState } from "react";

interface JsonEditorProps {
  label: string;
  value: unknown;
  textValue?: string;
  onSave?: (value: Record<string, unknown>) => void;
  onChange?: (value: string) => void;
  disabled?: boolean;
  errorMessage?: string | null;
}

function stringifyJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function localizedLabel(label: string): string {
  const labels: Record<string, string> = {
    Catalog: "카탈로그",
    Profile: "프로필",
    Scenarios: "시나리오",
    Workflow: "워크플로",
  };
  return labels[label] ?? label;
}

export function JsonEditor({
  label,
  value,
  textValue,
  onSave,
  onChange,
  disabled = false,
  errorMessage = null,
}: JsonEditorProps) {
  const [text, setText] = useState(() => textValue ?? stringifyJson(value));
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setText(textValue ?? stringifyJson(value));
    setError(null);
  }, [textValue, value]);

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
      const message = cause instanceof Error ? cause.message : "알 수 없는 구문 오류";
      setError(`${localizedLabel(label)} JSON이 올바르지 않습니다: ${message}`);
    }
  }

  const displayLabel = localizedLabel(label);

  return (
    <section className="workspace-panel editor-panel">
      <div className="section-header">
        <div>
          <p className="eyebrow">고급 편집</p>
          <h2>{displayLabel}</h2>
        </div>
        {onSave ? (
          <button
            className="button-secondary"
            type="button"
            onClick={handleSave}
            disabled={disabled}
          >
            {`${displayLabel} 저장`}
          </button>
        ) : null}
      </div>
      <label className="field">
        <span>{displayLabel} JSON</span>
        <textarea
          aria-label={`${displayLabel} JSON`}
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
