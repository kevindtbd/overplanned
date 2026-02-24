// UserAvatar -- Shared avatar component with image + initials fallback.
//
// Usage:
//   <UserAvatar name="Jane Doe" avatarUrl="/photo.jpg" size="md" />
//   <UserAvatar name="Jane Doe" size="sm" />  // Shows "J" fallback

interface UserAvatarProps {
  name: string | null;
  avatarUrl?: string | null;
  /** sm = 24px, md = 28px, lg = 32px */
  size?: "sm" | "md" | "lg";
  /** Extra border styling (e.g. for overlapping stacks) */
  borderClass?: string;
}

const SIZE_MAP = {
  sm: { px: 24, dims: "h-6 w-6", text: "text-[9px]" },
  md: { px: 28, dims: "h-7 w-7", text: "text-[10px]" },
  lg: { px: 32, dims: "h-8 w-8", text: "text-xs" },
} as const;

export function UserAvatar({
  name,
  avatarUrl,
  size = "md",
  borderClass,
}: UserAvatarProps) {
  const config = SIZE_MAP[size];
  const initial = name ? name.charAt(0).toUpperCase() : "?";
  const displayName = name ?? "Member";

  if (avatarUrl) {
    return (
      /* eslint-disable-next-line @next/next/no-img-element */
      <img
        src={avatarUrl}
        alt={displayName}
        className={`${config.dims} rounded-full object-cover shrink-0 ${borderClass ?? ""}`}
        style={{ width: config.px, height: config.px }}
      />
    );
  }

  return (
    <div
      className={`${config.dims} rounded-full bg-surface border border-ink-700 flex items-center justify-center shrink-0 font-dm-mono ${config.text} text-ink-300 ${borderClass ?? ""}`}
      style={{ width: config.px, height: config.px }}
      title={displayName}
      aria-hidden="true"
    >
      {initial}
    </div>
  );
}
