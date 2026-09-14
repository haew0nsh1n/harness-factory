interface StatusBadgeProps {
  label: string;
}

function toClassName(label: string): string {
  return `status-badge status-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
}

export function StatusBadge({ label }: StatusBadgeProps) {
  return <span className={toClassName(label)}>{label}</span>;
}
