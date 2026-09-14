import { Link } from 'react-router'

/** Shared notice for readers who cannot save personal progress. */
export function ReadOnlyNotice() {
  return (
    <p className="mt-5 text-sm text-muted-foreground">
      <Link to="/auth" className="text-primary underline-offset-4 hover:underline">
        Log in to track progress
      </Link>
    </p>
  )
}
