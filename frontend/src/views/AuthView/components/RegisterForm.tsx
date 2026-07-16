import { useState, type FormEvent } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useAuth } from '@/auth'
import type { SubmitStatus } from '../types'

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
  const [submit, setSubmit] = useState<SubmitStatus>({ phase: 'idle' })

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setSubmit({ phase: 'idle' })
    if (!values.username || !values.email || !values.password) {
      setSubmit({ phase: 'error', message: 'Choose a username, email, and password.', fields: {} })
      return
    }
    setSubmit({ phase: 'submitting' })
    const result = await register(values)
    if (result.ok) {
      setSubmit({ phase: 'idle' })
      return
    }
    setSubmit({ phase: 'error', message: result.message, fields: result.fields ?? {} })
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
        {submit.phase === 'error' && submit.fields.username && (
          <span className="text-sm text-destructive">{submit.fields.username}</span>
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
        {submit.phase === 'error' && submit.fields.email && (
          <span className="text-sm text-destructive">{submit.fields.email}</span>
        )}
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
        {submit.phase === 'submitting' ? 'Creating account...' : 'Create account'}
      </Button>
    </form>
  )
}
