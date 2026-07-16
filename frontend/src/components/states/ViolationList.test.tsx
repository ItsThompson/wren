import { render, screen } from '@testing-library/react'

import { ViolationList } from './ViolationList'

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
