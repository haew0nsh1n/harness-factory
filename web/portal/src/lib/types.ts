export type DesignStatus =
  | "draft"
  | "validated"
  | "approved"
  | "build-queued"
  | "built"
  | "failed";

export type ContentLanguage = "ko" | "en";

export type BuildStatus = "queued" | "running" | "succeeded" | "failed";

export type RegistryVersionStatus =
  | "draft"
  | "validated"
  | "in-review"
  | "approved"
  | "published"
  | "deprecated"
  | "revoked";

export type RegistryChannel = "unpublished" | "pilot" | "stable";

export interface ValidationFinding {
  field: string;
  code: string;
  message: string;
}

export interface HarnessDesign {
  id: string;
  organization_id: string;
  customer_id: string;
  name: string;
  language: ContentLanguage;
  profile: Record<string, unknown>;
  workflow: Record<string, unknown>;
  scenarios: Record<string, unknown>;
  catalog: Record<string, unknown>;
  revision: number;
  digest: string;
  status: DesignStatus;
  validation_findings: ValidationFinding[] | null;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface BuildJob {
  id: string;
  organization_id: string;
  design_id: string;
  design_digest: string;
  status: BuildStatus;
  attempts: number;
  artifact_key: string | null;
  artifact_digest: string | null;
  error_code: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  updated_at: string;
}

export interface RegistryVersionSummary {
  id: string;
  version: string;
  digest: string;
  status: string;
  channel: string;
  artifact_sha256: string;
}

export interface RegistryAssetSummary {
  id: string;
  type: string;
  slug: string;
  name: string;
  language: ContentLanguage;
  description: string | null;
  versions: RegistryVersionSummary[];
}

export interface RegistryActor {
  organization_id: string;
  subject_id: string;
  roles: string[];
}

export interface RegistryAssetCreate {
  id: string;
  organization_id: string;
  type: string;
  slug: string;
  name: string;
  language: ContentLanguage;
  description: string | null;
  owner_subject_id: string;
  visibility: string;
  lifecycle: string;
}

export interface RegistryVersionDetail extends RegistryVersionSummary {
  organization_id: string;
  asset_id: string;
  manifest: RegistryManifest;
}

export interface RegistryAssetDetail extends RegistryAssetSummary {
  organization_id: string;
  owner_subject_id: string;
  visibility: string;
  lifecycle: string;
}

export interface RegistryManifest {
  schema_version: number;
  asset: {
    type: string;
    slug: string;
  };
  version: string;
  runtime: string;
  design_digest: string;
  artifact: {
    sha256: string;
    key: string;
  };
  dependencies: unknown[];
}

export type InterviewStage =
  | "discovery"
  | "planning"
  | "implementation"
  | "testing"
  | "review"
  | "release"
  | "operations"
  | "summary";

export interface InterviewTurn {
  id: string;
  role: "user" | "assistant";
  text: string;
  sequence: number;
  created_at: string;
  options?: Array<{ id: string; label: string }>;
  allow_custom_answer?: boolean;
  choice_question_turn_id?: string | null;
  choice_option_id?: string | null;
}

export interface InterviewEvidence {
  id: string;
  statement: string;
  kind: "fact" | "assumption" | "unknown";
  source_turn_ids: string[];
}

export interface InterviewProposalSummary {
  id: string;
  revision: number;
  digest: string;
  status: string;
  findings: Array<Record<string, string>>;
  created_at: string;
  updated_at: string;
}

export interface InterviewProposal extends InterviewProposalSummary {
  profile: Record<string, unknown>;
  workflow: Record<string, unknown>;
  scenarios: Record<string, unknown>;
  catalog: Record<string, unknown>;
}

export interface InterviewSession {
  id: string;
  organization_id: string;
  owner_subject_id: string;
  name: string;
  customer_id: string;
  revision: number;
  status: "active" | "awaiting-confirmation" | "completed";
  consent_version: string;
  consented_at: string;
  stage: InterviewStage;
  /** Older sessions predate scoped interviews and therefore cover every SDLC stage. */
  selected_stages?: Exclude<InterviewStage, "summary">[];
  scope: string | null;
  proposed_evidence: InterviewEvidence[];
  confirmed_evidence: InterviewEvidence[];
  turns: InterviewTurn[];
  proposals: InterviewProposalSummary[];
  last_operation: {
    request_id: string;
    kind: string;
    status: string;
    /** Missing on legacy DTOs and therefore treated as false by the client. */
    lease_expired?: boolean;
  } | null;
  last_error_code: string | null;
  created_at: string;
  updated_at: string;
  expires_at: string;
}
