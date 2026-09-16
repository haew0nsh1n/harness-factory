"use client";

import {
  type ReactNode,
  useRef,
  useState,
} from "react";

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
  label = "디버그 JSON",
  hint = "원문 확인이나 복구가 필요할 때만 엽니다.",
  errors = [],
  focusTargetLabel,
}: DebugJsonDisclosureProps) {
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
          <strong>JSON 오류로 저장할 수 없습니다.</strong>
          <ul className={styles.errorList}>
            {errors.map((error, index) => (
              <li key={`${error}-${index}`}>{error}</li>
            ))}
          </ul>
          <button className={styles.fixButton} type="button" onClick={openToFix}>
            디버그 JSON 열고 수정
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
            <span className={styles.title}>{label}</span>
            <span className={styles.hint}>{hint}</span>
          </span>
        </summary>
        <div className={styles.content}>{children}</div>
      </details>
    </>
  );
}
