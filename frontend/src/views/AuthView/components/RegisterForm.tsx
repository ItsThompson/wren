import { useState, type FormEvent } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useAuth } from '@/auth'

interface Fields {
  username: string
  email: string
  password: string
}

const EMPTY: Fields = { username: '', email: '', password: '' }

/**
 * Register with username + email + password. A duplicate handle/email or a weak
 * password comes back as a field-level RFC 9457 problem, so the offending field
 * shows its own message under the input.
 */
export function RegisterForm() {
  const { register } = useAuth()
  const [values, setValues] = useState<Fields>(EMPTY)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    setFieldErrors({})
    if (!values.username || !values.email || !values.password) {
      setError('Choose a username, email, and password.')
      return
    }
    setSubmitting(true)
    const result = await register(values)
    setSubmitting(false)
    if (!result.ok) {
      setError(result.message)
      if (result.fields) setFieldErrors(result.fields)
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      <label className="flex flex-col gap-1.5 text-sm">
        <span className="font-medium text-foreground">Username</span>
        <Input
          name="username"
          autoComplete="username"
          value={values.username}
          onChange={(event) => setValues((prev) => ({ ...prev, username: event.target.value }))}
        />
        {fieldErrors.username && (
          <span className="text-sm text-destructive">{fieldErrors.username}</span>
        )}
      </label>
      <label className="flex flex-col gap-1.5 text-sm">
        <span className="font-medium text-foreground">Email</span>
        <Input
          type="email"
          name="email"
          autoComplete="email"
          value={values.email}
          onChange={(event) => setValues((prev) => ({ ...prev, email: event.target.value }))}
        />
        {fieldErrors.email && <span className="text-sm text-destructive">{fieldErrors.email}</span>}
      </label>
      <label className="flex flex-col gap-1.5 text-sm">
        <span className="font-medium text-foreground">Password</span>
        <Input
          type="password"
          name="password"
          autoComplete="new-password"
          value={values.password}
          onChange={(event) => setValues((prev) => ({ ...prev, password: event.target.value }))}
        />
        {fieldErrors.password && (
          <span className="text-sm text-destructive">{fieldErrors.password}</span>
        )}
      </label>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      <Button type="submit" disabled={submitting}>
        {submitting ? 'Creating account...' : 'Create account'}
      </Button>
    </form>
  )
}
