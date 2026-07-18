import { resolveStartDestination } from './resolveStartDestination'

describe('resolveStartDestination', () => {
  it('sends an authenticated visitor to the dashboard', () => {
    expect(resolveStartDestination('authenticated')).toBe('/dashboard')
  })

  it('sends an anonymous visitor to signup in register mode', () => {
    expect(resolveStartDestination('anonymous')).toBe('/auth?mode=register')
  })
})
