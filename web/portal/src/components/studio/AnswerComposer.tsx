"use client";

import { useEffect, useState } from "react";

import { useTranslations } from "@/i18n/I18nProvider";
import type { InterviewTurn } from "@/lib/types";

interface AnswerComposerProps {
  question: InterviewTurn | null;
  answer: string;
  busy: boolean;
  retryAvailable: boolean;
  onAnswerChange: (value: string) => void;
  onSendAnswer: () => void;
  onSendChoice: (questionTurnId: string, optionId: string) => void;
  onRetry: () => void;
}

type AnswerSelection =
  | { mode: "custom" }
  | { mode: "option"; optionId: string };

export function AnswerComposer({
  question,
  answer,
  busy,
  retryAvailable,
  onAnswerChange,
  onSendAnswer,
  onSendChoice,
  onRetry,
}: AnswerComposerProps) {
  const t = useTranslations();
  const [selection, setSelection] = useState<AnswerSelection>({
    mode: "custom",
  });
  const options = question?.options ?? [];
  const allowCustom = question?.allow_custom_answer ?? true;

  useEffect(() => {
    setSelection(
      allowCustom
        ? { mode: "custom" }
        : options[0]
          ? { mode: "option", optionId: options[0].id }
          : { mode: "custom" },
    );
  }, [question?.id, allowCustom, options[0]?.id]);

  const selectedOption =
    selection.mode === "option"
      ? options.find((option) => option.id === selection.optionId)
      : null;
  const isCustom = selection.mode === "custom";

  return (
    <div className="answer-composer">
      {question && options.length > 0 ? (
        <fieldset className="answer-options">
          <legend>{t("answerComposer.aiSuggestion")}</legend>
          <p>{t("answerComposer.suggestionNote")}</p>
          <div className="choice-grid" role="radiogroup" aria-label={t("answerComposer.aiSuggestionAria")}>
            {options.map((option) => (
              <label className="choice-control answer-option" key={option.id}>
                <input
                  type="radio"
                  name={`question-${question.id}`}
                  value={`option:${option.id}`}
                  checked={
                    selection.mode === "option" &&
                    selection.optionId === option.id
                  }
                  disabled={busy}
                  onChange={() =>
                    setSelection({ mode: "option", optionId: option.id })
                  }
                />
                <span>{option.label}</span>
              </label>
            ))}
            {allowCustom ? (
              <label className="choice-control answer-option">
                <input
                  type="radio"
                  name={`question-${question.id}`}
                  value="custom-answer"
                  checked={isCustom}
                  disabled={busy}
                  onChange={() => setSelection({ mode: "custom" })}
                />
                <span>{t("answerComposer.customInput")}</span>
              </label>
            ) : null}
          </div>
        </fieldset>
      ) : null}
      {isCustom ? (
        <label className="field">
          <span>{t("answerComposer.answerLabel")}</span>
          <textarea
            aria-label={t("answerComposer.answerLabel")}
            rows={5}
            maxLength={8000}
            value={answer}
            disabled={busy}
            onChange={(event) => onAnswerChange(event.target.value)}
            placeholder={t("answerComposer.answerPlaceholder")}
          />
        </label>
      ) : null}
      <div className="composer-actions">
        <span>{isCustom ? t("answerComposer.customHint", { count: answer.length }) : t("answerComposer.optionHint")}</span>
        <button
          className="button-primary"
          type="button"
          disabled={busy || (isCustom ? !answer.trim() : !selectedOption || !question)}
          onClick={() => {
            if (isCustom) {
              onSendAnswer();
            } else if (question && selectedOption) {
              onSendChoice(question.id, selectedOption.id);
            }
          }}
        >
          {t("answerComposer.sendAnswer")}
        </button>
        {retryAvailable ? (
          <button className="button-secondary" type="button" disabled={busy} onClick={onRetry}>
            {t("answerComposer.retry")}
          </button>
        ) : null}
      </div>
    </div>
  );
}
