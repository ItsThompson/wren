import { useState, type FormEvent } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useAuth } from '@/auth'

interface Credentials {
  email: string
  password: string
}

const EMPTY: Credentials = { email: '', password: '' }

/**
 * Email + password login. Field-level RFC 9457 errors attach to their input;
 * a wrong-credentials 401 renders as a single generic message (the backend
 * never says whether the email exists).
 */
export function LoginForm() {
  const { login } = useAuth()
  const [values, setValues] = useState<Credentials>(EMPTY)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    setFieldErrors({})
    if (!values.email || !values.password) {
      setError('Enter your email and password.')
      return
    }
    setSubmitting(true)
    const result = await login(values)
    setSubmitting(false)
    if (!result.ok) {
      setError(result.message)
      if (result.fields) setFieldErrors(result.fields)
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
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
          autoComplete="current-password"
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
        {submitting ? 'Logging in...' : 'Log in'}
      </Button>
    </form>
  )
}
