"use client";

import { useEffect, useState } from "react";

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
          <legend>AI 제안</legend>
          <p>제안은 사실이 아닙니다. 내용을 확인한 뒤 선택하거나 직접 답변하세요.</p>
          <div className="choice-grid" role="radiogroup" aria-label="AI 제안 답변">
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
                <span>직접 입력</span>
              </label>
            ) : null}
          </div>
        </fieldset>
      ) : null}
      {isCustom ? (
        <label className="field">
          <span>답변</span>
          <textarea
            aria-label="답변"
            rows={5}
            maxLength={8000}
            value={answer}
            disabled={busy}
            onChange={(event) => onAnswerChange(event.target.value)}
            placeholder="확인 가능한 사실과 아직 모르는 내용을 구분해 입력하세요."
          />
        </label>
      ) : null}
      <div className="composer-actions">
        <span>{isCustom ? `${answer.length}/8000 · 입력 중에는 모델을 호출하지 않습니다.` : "선택 후 전송을 눌러야 답변이 전송됩니다."}</span>
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
          답변 보내기
        </button>
        {retryAvailable ? (
          <button className="button-secondary" type="button" disabled={busy} onClick={onRetry}>
            저장된 요청 다시 시도
          </button>
        ) : null}
      </div>
    </div>
  );
}
