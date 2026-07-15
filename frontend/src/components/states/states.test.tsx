import { fireEvent, render, screen } from '@testing-library/react'

import {
  EmptyState,
  ErrorState,
  ImmutableNotice,
  InlineNotice,
  StaleRevisionNotice,
  ViolationList,
} from './index'

describe('EmptyState', () => {
  it('renders the Fraunces title, sub-line, and a single action', () => {
    render(
      <EmptyState
        title="Nothing here yet."
        description="Start your first roadmap."
        action={<a href="/x">Get started</a>}
      />,
    )
    expect(screen.getByText('Nothing here yet.')).toHaveClass('display-m')
    expect(screen.getByText('Start your first roadmap.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Get started' })).toHaveAttribute('href', '/x')
  })

  it('omits the sub-line and action when not provided', () => {
    render(<EmptyState title="No published roadmaps yet." />)
    expect(screen.getByText('No published roadmaps yet.')).toBeInTheDocument()
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })
})

describe('ErrorState', () => {
  it('renders a title as an alert with a recovery action', () => {
    render(
      <ErrorState
        title="Roadmap not found"
        description="This roadmap does not exist or is not shared with you."
        action={<button type="button">Try again</button>}
      />,
    )
    // role="alert" carries meaning to assistive tech (never color alone).
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('Roadmap not found')
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })
})

describe('StaleRevisionNotice', () => {
  it('surfaces an ochre re-read prompt with a reload action (color AND text)', () => {
    const onReload = vi.fn()
    render(<StaleRevisionNotice onReload={onReload} />)

    const alert = screen.getByRole('alert')
    // Meaning is in the text, not just the ochre surface.
    expect(alert).toHaveTextContent(/reload to continue/i)
    // The ochre reinforcement is present on the surface classes.
    expect(alert.className).toMatch(/warning/)

    fireEvent.click(screen.getByRole('button', { name: 'Reload' }))
    expect(onReload).toHaveBeenCalledTimes(1)
  })

  it('shows the server detail when provided', () => {
    render(<StaleRevisionNotice detail="Revision 12 -> 13; re-read." onReload={vi.fn()} />)
    expect(screen.getByText('Revision 12 -> 13; re-read.')).toBeInTheDocument()
  })
})

describe('ImmutableNotice', () => {
  it('offers a fork action and explains why in text', () => {
    const onFork = vi.fn()
    render(<ImmutableNotice onFork={onFork} />)

    expect(screen.getByRole('alert')).toHaveTextContent(/fork it to make changes/i)
    fireEvent.click(screen.getByRole('button', { name: 'Fork to change' }))
    expect(onFork).toHaveBeenCalledTimes(1)
  })

  it('disables and relabels the action while forking', () => {
    render(<ImmutableNotice onFork={vi.fn()} forking />)
    expect(screen.getByRole('button', { name: 'Forking…' })).toBeDisabled()
  })

  it('renders without an action when no fork handler is given', () => {
    render(<ImmutableNotice />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})

describe('ViolationList', () => {
  it('renders each violation as text: rule, message, and offending ids', () => {
    render(
      <ViolationList
        violations={[
          {
            rule: 'V7_RESOURCE_REQUIRED',
            ids: ['sub_hashing'],
            message: 'subsection sub_hashing has no resources',
          },
          { rule: 'V3_ACYCLIC', ids: ['sub_a', 'sub_b'], message: 'prerequisite cycle detected' },
        ]}
      />,
    )
    // The count is announced and each rule/message/id set is readable text.
    expect(screen.getByRole('alert')).toHaveTextContent('Fix 2 issues:')
    expect(screen.getByText('V7_RESOURCE_REQUIRED')).toBeInTheDocument()
    expect(screen.getByText('subsection sub_hashing has no resources')).toBeInTheDocument()
    expect(screen.getByText('sub_a, sub_b')).toBeInTheDocument()
  })

  it('uses the singular form for one violation', () => {
    render(<ViolationList violations={[{ rule: 'r', ids: [], message: 'm' }]} />)
    expect(screen.getByRole('alert')).toHaveTextContent('Fix 1 issue:')
  })
})

describe('InlineNotice', () => {
  it('renders a polite status message and a dismiss control', () => {
    const onDismiss = vi.fn()
    render(<InlineNotice onDismiss={onDismiss}>We couldn’t save your progress.</InlineNotice>)

    expect(screen.getByRole('status')).toHaveTextContent('We couldn’t save your progress.')
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }))
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })
})
