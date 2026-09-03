import { cn } from "@/lib/utils"
import { userAvatarTone, userInitials } from "@/lib/user-avatar"

export function UserAvatar({ name, className }: { name: string | null | undefined; className?: string }) {
  const initials = userInitials(name)
  return (
    <span
      className={cn("user-avatar", `user-avatar--tone-${userAvatarTone(name)}`, className)}
      aria-hidden="true"
      data-initials={initials}
    >
      {initials}
    </span>
  )
}
