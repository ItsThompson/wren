import { useState, type FormEvent } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useAuth } from '@/auth'
import type { SubmitStatus } from '../types'

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
  const [submit, setSubmit] = useState<SubmitStatus>({ phase: 'idle' })

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setSubmit({ phase: 'idle' })
    if (!values.email || !values.password) {
      setSubmit({ phase: 'error', message: 'Enter your email and password.', fields: {} })
      return
    }
    setSubmit({ phase: 'submitting' })
    const result = await login(values)
    if (result.ok) {
      setSubmit({ phase: 'idle' })
      return
    }
    setSubmit({ phase: 'error', message: result.message, fields: result.fields ?? {} })
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
        {submit.phase === 'error' && submit.fields.email && (
          <span className="text-sm text-destructive">{submit.fields.email}</span>
        )}
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
        {submit.phase === 'error' && submit.fields.password && (
          <span className="text-sm text-destructive">{submit.fields.password}</span>
        )}
      </label>
      {submit.phase === 'error' && (
        <p role="alert" className="text-sm text-destructive">
          {submit.message}
        </p>
      )}
      <Button type="submit" disabled={submit.phase === 'submitting'}>
        {submit.phase === 'submitting' ? 'Logging in...' : 'Log in'}
      </Button>
    </form>
  )
}
