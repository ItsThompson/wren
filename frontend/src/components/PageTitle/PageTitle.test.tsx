import { render, screen } from '@testing-library/react'

import { DEFAULT_DOCUMENT_TITLE, PageTitle } from './PageTitle'

describe('PageTitle', () => {
  it('uses the Wren default when no title is provided', () => {
    render(
      <PageTitle>
        <p>content</p>
      </PageTitle>,
    )

    expect(screen.getByText('content')).toBeInTheDocument()
    expect(document.title).toBe(DEFAULT_DOCUMENT_TITLE)
  })

  it('prefixes a specific page title with Wren', () => {
    render(<PageTitle title="Dashboard" />)

    expect(document.title).toBe('Wren: Dashboard')
  })
})
