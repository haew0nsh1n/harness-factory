import { StudioDesignPageContent } from "@/components/StudioDesignPageContent";

interface StudioDesignPageProps {
  params: Promise<{
    id: string;
  }>;
}

export default async function StudioDesignPage(props: StudioDesignPageProps) {
  const params = await props.params;
  return <StudioDesignPageContent designId={params.id} />;
}
