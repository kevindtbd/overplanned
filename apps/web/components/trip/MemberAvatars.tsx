interface Member {
  id: string;
  userId: string;
  role: string;
  status: string;
  user: {
    id: string;
    name: string | null;
    avatarUrl: string | null;
  };
}

interface Props {
  members: Member[];
  maxVisible?: number;
}

export function MemberAvatars({ members, maxVisible = 4 }: Props) {
  const joined = members.filter((m) => m.status === "joined");
  if (joined.length <= 1) return null;

  const visible = joined.slice(0, maxVisible);
  const overflow = joined.length - maxVisible;

  return (
    <div className="flex items-center -space-x-2">
      {visible.map((m) => (
        <div
          key={m.id}
          className="relative h-7 w-7 rounded-full border-2 border-base bg-surface"
          title={m.user.name ?? "Member"}
        >
          {m.user.avatarUrl ? (
            /* eslint-disable-next-line @next/next/no-img-element */
            <img
              src={m.user.avatarUrl}
              alt={m.user.name ?? ""}
              className="h-full w-full rounded-full object-cover"
            />
          ) : (
            <span className="flex h-full w-full items-center justify-center font-dm-mono text-[10px] text-ink-300">
              {(m.user.name ?? "?")[0].toUpperCase()}
            </span>
          )}
        </div>
      ))}
      {overflow > 0 && (
        <div className="relative flex h-7 w-7 items-center justify-center rounded-full border-2 border-base bg-surface font-dm-mono text-[10px] text-ink-300">
          +{overflow}
        </div>
      )}
    </div>
  );
}
