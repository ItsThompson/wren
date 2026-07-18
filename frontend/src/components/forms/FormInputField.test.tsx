import { render, screen } from '@testing-library/react'

import { FormInputField } from './FormInputField'

describe('FormInputField', () => {
  it('renders an input with an accessible label', () => {
    render(<FormInputField label="Email" name="email" />)

    expect(screen.getByRole('textbox', { name: 'Email' })).toHaveAttribute('name', 'email')
  })

  it('attaches a field-level error to the input', () => {
    render(<FormInputField label="Email" name="email" error="This email is already registered." />)

    const input = screen.getByRole('textbox', { name: 'Email' })
    const error = screen.getByText('This email is already registered.')

    expect(input).toHaveAttribute('aria-invalid', 'true')
    expect(input).toHaveAttribute('aria-describedby', error.id)
  })

  it('preserves existing descriptive text when showing an error', () => {
    render(
      <>
        <p id="email-help">Use the address you check most often.</p>
        <FormInputField
          id="email"
          label="Email"
          name="email"
          aria-describedby="email-help"
          error="Enter a valid email address."
        />
      </>,
    )

    expect(screen.getByRole('textbox', { name: 'Email' })).toHaveAttribute(
      'aria-describedby',
      'email-help email-error',
    )
  })

  it('generates unique ids when repeated fields share a name', () => {
    render(
      <>
        <FormInputField label="Email" name="email" error="First email error." />
        <FormInputField label="Email" name="email" error="Second email error." />
      </>,
    )

    const [firstInput, secondInput] = screen.getAllByRole('textbox', { name: 'Email' })

    expect(firstInput.id).not.toBe(secondInput.id)
    expect(firstInput.getAttribute('aria-describedby')).not.toBe(
      secondInput.getAttribute('aria-describedby'),
    )
  })
})
