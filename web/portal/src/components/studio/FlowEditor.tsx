"use client";

import { useState } from "react";

import { Modal } from "@/components/studio/Modal";
import { useTranslations } from "@/i18n/I18nProvider";

export interface FlowItem {
  key: string;
  label: string;
  removeLabel: string;
  onRemove: () => void;
  content: React.ReactNode;
}

// Arrow-connected overview of workflow steps or SDLC stages. Each node opens a
// modal that hosts the item's full editor, keeping the section compact.
export function FlowEditor({
  title,
  ariaLabel,
  addLabel,
  onAdd,
  items,
  error,
}: {
  title: string;
  ariaLabel: string;
  addLabel: string;
  onAdd: () => void;
  items: FlowItem[];
  error?: string;
}): React.JSX.Element {
  const t = useTranslations();
  const [openKey, setOpenKey] = useState<string | null>(null);
  const open = items.find((item) => item.key === openKey) ?? null;

  return (
    <section className="nested-form-section flow-editor">
      <div className="nested-field-heading">
        <h3>{title}</h3>
        <button
          className="button-secondary button-compact"
          type="button"
          onClick={onAdd}
        >
          {addLabel}
        </button>
      </div>
      {error ? <p className="field-error">{error}</p> : null}
      {items.length === 0 ? (
        <p className="muted">{t("flowEdit.empty")}</p>
      ) : (
        <nav className="flow-diagram" aria-label={ariaLabel}>
          {items.map((item, index) => (
            <div className="flow-node-wrap" key={item.key}>
              {index > 0 ? (
                <span className="flow-arrow" aria-hidden="true" />
              ) : null}
              <button
                type="button"
                className="flow-node"
                aria-haspopup="dialog"
                onClick={() => setOpenKey(item.key)}
              >
                <span className="flow-node-index" aria-hidden="true">
                  {index + 1}
                </span>
                <span className="flow-node-label">{item.label}</span>
                <span className="flow-node-edit">{t("flowEdit.edit")}</span>
              </button>
            </div>
          ))}
        </nav>
      )}
      {open ? (
        <Modal
          title={open.label}
          onClose={() => setOpenKey(null)}
          closeLabel={t("flowEdit.close")}
        >
          <div className="flow-modal-fields">{open.content}</div>
          <div className="flow-modal-actions">
            <button
              type="button"
              className="button-secondary button-compact"
              onClick={() => {
                open.onRemove();
                setOpenKey(null);
              }}
            >
              {open.removeLabel}
            </button>
            <button
              type="button"
              className="button-primary"
              onClick={() => setOpenKey(null)}
            >
              {t("flowEdit.done")}
            </button>
          </div>
        </Modal>
      ) : null}
    </section>
  );
}
