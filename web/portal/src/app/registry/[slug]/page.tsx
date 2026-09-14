import { RegistryDetailPageContent } from "@/components/RegistryDetailPageContent";

interface RegistryDetailPageProps {
  params: Promise<{
    slug: string;
  }>;
}

export default async function RegistryDetailPage(props: RegistryDetailPageProps) {
  const params = await props.params;
  return <RegistryDetailPageContent slug={params.slug} />;
}
