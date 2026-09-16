import { InterviewPageContent } from "@/components/studio/InterviewPageContent";

interface InterviewPageProps {
  params: Promise<{ id: string }>;
}

export default async function InterviewPage({ params }: InterviewPageProps) {
  const { id } = await params;
  return <InterviewPageContent interviewId={id} />;
}
