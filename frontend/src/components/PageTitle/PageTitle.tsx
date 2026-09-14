import type { ReactNode } from 'react'
import { useEffect } from 'react'

export const DEFAULT_DOCUMENT_TITLE = 'Wren: learn anything, in the right order'

interface PageTitleProps {
  title?: string
  children?: ReactNode
}

export function PageTitle({ title, children }: PageTitleProps) {
  useEffect(() => {
    document.title = title ? `Wren: ${title}` : DEFAULT_DOCUMENT_TITLE
  }, [title])

  return children ?? null
}
