"use client";

import type { ReactNode } from "react";

import { isJsonDocument, type JsonDocument } from "@/lib/designForms";

export function displayText(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  if (value === null || value === undefined) {
    return "";
  }
  return JSON.stringify(value);
}

export interface IndexedRow<T> {
  originalIndex: number;
  value: T;
}

export function objectRows(value: unknown): IndexedRow<JsonDocument>[] {
  return Array.isArray(value)
    ? value.flatMap((item, originalIndex) =>
        isJsonDocument(item) ? [{ originalIndex, value: item }] : [],
      )
    : [];
}

export function stringRows(value: unknown): IndexedRow<string>[] {
  return Array.isArray(value)
    ? value.map((item, originalIndex) => ({
        originalIndex,
        value: displayText(item),
      }))
    : [];
}

export function appendRow(value: unknown, next: unknown): unknown[] {
  return Array.isArray(value) ? [...value, next] : [next];
}

export function replaceRow(
  value: unknown,
  originalIndex: number,
  next: unknown,
): unknown[] {
  return Array.isArray(value)
    ? value.map((row, rowIndex) => (rowIndex === originalIndex ? next : row))
    : [next];
}

export function removeRow(value: unknown, originalIndex: number): unknown[] {
  return Array.isArray(value)
    ? value.filter((_, rowIndex) => rowIndex !== originalIndex)
    : [];
}

interface FieldShellProps {
  label: string;
  error?: string;
  children: ReactNode;
}

export function FieldShell({ label, error, children }: FieldShellProps) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {error ? <span className="field-error">{error}</span> : null}
    </label>
  );
}

interface TextFieldProps {
  label: string;
  value: unknown;
  onChange: (value: string) => void;
  error?: string;
  multiline?: boolean;
  onBlur?: () => void;
}

export function TextField({
  label,
  value,
  onChange,
  error,
  multiline = false,
  onBlur,
}: TextFieldProps) {
  const props = {
    "aria-invalid": Boolean(error),
    "aria-label": label,
    value: displayText(value),
    onChange: (
      event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>,
    ) => onChange(event.target.value),
    onBlur,
  };
  return (
    <FieldShell label={label} error={error}>
      {multiline ? <textarea {...props} rows={3} /> : <input {...props} />}
    </FieldShell>
  );
}

interface SelectFieldProps {
  label: string;
  value: unknown;
  options: readonly string[];
  onChange: (value: string) => void;
  error?: string;
}

export function SelectField({
  label,
  value,
  options,
  onChange,
  error,
}: SelectFieldProps) {
  const current = displayText(value);
  const known = options.includes(current);
  return (
    <FieldShell label={label} error={error}>
      <select
        aria-label={label}
        aria-invalid={Boolean(error)}
        value={current}
        onChange={(event) => onChange(event.target.value)}
      >
        {!known ? <option value={current}>현재 값: {current || "(비어 있음)"}</option> : null}
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </FieldShell>
  );
}

interface StringListFieldProps {
  label: string;
  value: unknown;
  onChange: (value: string[]) => void;
  error?: string;
}

export function StringListField({
  label,
  value,
  onChange,
  error,
}: StringListFieldProps) {
  const rows = stringRows(value);
  return (
    <div className="nested-field-group">
      <div className="nested-field-heading">
        <strong>{label}</strong>
        <button
          className="button-secondary button-compact"
          type="button"
          onClick={() => onChange(appendRow(value, "") as string[])}
        >
          항목 추가
        </button>
      </div>
      {!Array.isArray(value) && value !== undefined ? (
        <p className="field-error">{error ?? "현재 값은 목록이어야 합니다. 원본은 유지됩니다."}</p>
      ) : null}
      {rows.map((row) => (
        <div className="inline-edit-row" key={`${label}-${row.originalIndex}`}>
          <TextField
            label={`${label} ${row.originalIndex + 1}`}
            value={row.value}
            onChange={(next) =>
              onChange(
                replaceRow(value, row.originalIndex, next) as string[],
              )
            }
          />
          <button
            className="button-secondary button-compact"
            type="button"
            aria-label={`${label} ${row.originalIndex + 1} 삭제`}
            onClick={() =>
              onChange(removeRow(value, row.originalIndex) as string[])
            }
          >
            삭제
          </button>
        </div>
      ))}
      {error && Array.isArray(value) ? <p className="field-error">{error}</p> : null}
    </div>
  );
}

export function ObjectListSection({
  title,
  error,
  onAdd,
  children,
}: {
  title: string;
  error?: string;
  onAdd: () => void;
  children: ReactNode;
}) {
  return (
    <section className="nested-form-section">
      <div className="nested-field-heading">
        <h3>{title}</h3>
        <button className="button-secondary button-compact" type="button" onClick={onAdd}>
          항목 추가
        </button>
      </div>
      {error ? <p className="field-error">{error}</p> : null}
      <div className="nested-card-list">{children}</div>
    </section>
  );
}

export function NestedCard({
  title,
  removeLabel,
  onRemove,
  children,
}: {
  title: string;
  removeLabel: string;
  onRemove: () => void;
  children: ReactNode;
}) {
  return (
    <fieldset className="nested-card">
      <legend>{title}</legend>
      <div className="nested-card-fields">{children}</div>
      <button
        className="button-secondary button-compact"
        type="button"
        aria-label={removeLabel}
        onClick={onRemove}
      >
        삭제
      </button>
    </fieldset>
  );
}
