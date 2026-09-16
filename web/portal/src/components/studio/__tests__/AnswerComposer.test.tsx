import { fireEvent, render, screen } from "@testing-library/react";

import { AnswerComposer } from "@/components/studio/AnswerComposer";
import type { InterviewTurn } from "@/lib/types";

const question: InterviewTurn = {
  id: "question-1",
  role: "assistant",
  text: "어떤 방식을 선택하시겠어요?",
  sequence: 1,
  created_at: "2026-09-16T00:00:00Z",
  options: [{ id: "custom", label: "Custom 옵션" }],
  allow_custom_answer: true,
};

function renderComposer(answer: string) {
  const onSendAnswer = vi.fn();
  const onSendChoice = vi.fn();
  const onAnswerChange = vi.fn();
  render(
    <AnswerComposer
      question={question}
      answer={answer}
      busy={false}
      retryAvailable={false}
      onAnswerChange={onAnswerChange}
      onSendAnswer={onSendAnswer}
      onSendChoice={onSendChoice}
      onRetry={vi.fn()}
    />,
  );
  return { onSendAnswer, onSendChoice, onAnswerChange };
}

test.each(["", "작성 중인 직접 답변"])(
  "sends the option whose id is custom instead of treating it as custom input (draft %j)",
  (draft) => {
    const handlers = renderComposer(draft);

    fireEvent.click(screen.getByRole("radio", { name: "Custom 옵션" }));
    fireEvent.click(screen.getByRole("button", { name: "답변 보내기" }));

    expect(handlers.onSendChoice).toHaveBeenCalledWith("question-1", "custom");
    expect(handlers.onSendAnswer).not.toHaveBeenCalled();
  },
);

test("preserves the custom draft when returning from an option to custom input", () => {
  const handlers = renderComposer("보존할 직접 답변");

  fireEvent.click(screen.getByRole("radio", { name: "Custom 옵션" }));
  expect(screen.queryByLabelText("답변")).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("radio", { name: "직접 입력" }));

  expect(screen.getByLabelText("답변")).toHaveValue("보존할 직접 답변");
  expect(handlers.onAnswerChange).not.toHaveBeenCalled();
});
