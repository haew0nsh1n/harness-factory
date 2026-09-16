"use client";

import { useEffect, useState } from "react";

import { useTranslations } from "@/i18n/I18nProvider";

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

export function JsonEditor({
  label,
  value,
  textValue,
  onSave,
  onChange,
  disabled = false,
  errorMessage = null,
}: JsonEditorProps) {
  const t = useTranslations();
  const labelKey = `jsonEditor.labels.${label}`;
  const translatedLabel = t(labelKey);
  const displayLabel = translatedLabel === labelKey ? label : translatedLabel;
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
      const message = cause instanceof Error ? cause.message : t("jsonEditor.unknownSyntaxError");
      setError(t("jsonEditor.invalidJson", { label: displayLabel, message }));
    }
  }

  return (
    <section className="workspace-panel editor-panel">
      <div className="section-header">
        <div>
          <p className="eyebrow">{t("jsonEditor.advancedEdit")}</p>
          <h2>{displayLabel}</h2>
        </div>
        {onSave ? (
          <button
            className="button-secondary"
            type="button"
            onClick={handleSave}
            disabled={disabled}
          >
            {t("jsonEditor.save", { label: displayLabel })}
          </button>
        ) : null}
      </div>
      <label className="field">
        <span>{t("jsonEditor.jsonSuffix", { label: displayLabel })}</span>
        <textarea
          aria-label={t("jsonEditor.jsonSuffix", { label: displayLabel })}
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
