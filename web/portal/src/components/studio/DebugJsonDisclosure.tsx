"use client";

import {
  type ReactNode,
  useRef,
  useState,
} from "react";

import { useTranslations } from "@/i18n/I18nProvider";

import styles from "./DebugJsonDisclosure.module.css";

interface DebugJsonDisclosureProps {
  children: ReactNode;
  label?: string;
  hint?: string;
  errors?: string[];
  focusTargetLabel?: string;
}

export function DebugJsonDisclosure({
  children,
  label,
  hint,
  errors = [],
  focusTargetLabel,
}: DebugJsonDisclosureProps) {
  const t = useTranslations();
  const displayLabel = label ?? t("debugJson.defaultLabel");
  const displayHint = hint ?? t("debugJson.defaultHint");
  const [open, setOpen] = useState(false);
  const detailsRef = useRef<HTMLDetailsElement>(null);

  function openToFix(): void {
    setOpen(true);
    requestAnimationFrame(() => {
      const target = Array.from(
        detailsRef.current?.querySelectorAll<HTMLElement>("textarea") ?? [],
      ).find(
        (element) =>
          !focusTargetLabel ||
          element.getAttribute("aria-label") === focusTargetLabel,
      );
      target?.focus();
    });
  }

  return (
    <>
      {errors.length > 0 ? (
        <div className={styles.errorSummary} role="alert">
          <strong>{t("debugJson.cannotSave")}</strong>
          <ul className={styles.errorList}>
            {errors.map((error, index) => (
              <li key={`${error}-${index}`}>{error}</li>
            ))}
          </ul>
          <button className={styles.fixButton} type="button" onClick={openToFix}>
            {t("debugJson.openAndFix")}
          </button>
        </div>
      ) : null}
      <details
        className={styles.disclosure}
        open={open}
        ref={detailsRef}
        onToggle={(event) => setOpen(event.currentTarget.open)}
      >
        <summary className={styles.summary}>
          <span>
            <span className={styles.title}>{displayLabel}</span>
            <span className={styles.hint}>{displayHint}</span>
          </span>
        </summary>
        <div className={styles.content}>{children}</div>
      </details>
    </>
  );
}
