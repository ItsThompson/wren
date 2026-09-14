import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { ToggleGroup, ToggleGroupItem } from './toggle-group'

describe('ToggleGroup', () => {
  it('supports controlled single selection and arrow-key navigation', async () => {
    const user = userEvent.setup()
    const onValueChange = vi.fn()
    render(
      <ToggleGroup type="single" value="any" onValueChange={onValueChange} aria-label="Match mode">
        <ToggleGroupItem value="any">ANY</ToggleGroupItem>
        <ToggleGroupItem value="all">ALL</ToggleGroupItem>
      </ToggleGroup>,
    )

    const any = screen.getByRole('radio', { name: 'ANY' })
    const all = screen.getByRole('radio', { name: 'ALL' })
    expect(any).toHaveAttribute('aria-checked', 'true')
    expect(all).toHaveAttribute('aria-checked', 'false')

    await user.click(all)
    expect(onValueChange).toHaveBeenCalledWith('all')
    await user.keyboard('{ArrowLeft}')
    expect(document.activeElement).toBe(any)
  })

  it('allows disabled items to remain unselectable', async () => {
    const user = userEvent.setup()
    render(
      <ToggleGroup type="single" defaultValue="any" aria-label="Match mode">
        <ToggleGroupItem value="any">ANY</ToggleGroupItem>
        <ToggleGroupItem value="all" disabled>
          ALL
        </ToggleGroupItem>
      </ToggleGroup>,
    )

    const all = screen.getByRole('radio', { name: 'ALL' })
    await user.click(all)
    expect(all).toHaveAttribute('aria-checked', 'false')
    expect(all).toBeDisabled()
  })
})
