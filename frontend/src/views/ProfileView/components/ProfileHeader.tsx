interface ProfileHeaderProps {
  displayName: string
  handle: string
}

/**
 * The profile header (design language §8 Profile): the display name set in the
 * warm Fraunces serif (the one human moment on the page) with the handle beneath
 * it in monospace.
 */
export function ProfileHeader({ displayName, handle }: ProfileHeaderProps) {
  return (
    <header className="border-b border-border pb-6">
      <h1 className="display-l text-foreground">{displayName}</h1>
      <p className="mt-1 font-mono text-sm text-muted-foreground">@{handle}</p>
    </header>
  )
}
