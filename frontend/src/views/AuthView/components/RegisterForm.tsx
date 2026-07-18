import { useEffect, useRef, useState, type FormEvent } from 'react'

import { useAuth } from '@/auth'
import { FormInputField } from '@/components/forms/FormInputField'
import { Button } from '@/components/ui/button'
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
  const usernameRef = useRef<HTMLInputElement>(null)
  const emailRef = useRef<HTMLInputElement>(null)
  const passwordRef = useRef<HTMLInputElement>(null)
  const fieldErrors = submit.phase === 'error' ? submit.fields : {}
  const hasFieldErrors = Object.values(fieldErrors).some(Boolean)

  useEffect(() => {
    if (submit.phase !== 'error') return
    if (submit.fields.username) {
      usernameRef.current?.focus()
      return
    }
    if (submit.fields.email) {
      emailRef.current?.focus()
      return
    }
    if (submit.fields.password) passwordRef.current?.focus()
  }, [submit])

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
      <FormInputField
        ref={usernameRef}
        label="Username"
        name="username"
        autoComplete="username"
        value={values.username}
        error={fieldErrors.username}
        onChange={(event) => setValues((prev) => ({ ...prev, username: event.target.value }))}
      />
      <FormInputField
        ref={emailRef}
        label="Email"
        type="email"
        name="email"
        autoComplete="email"
        value={values.email}
        error={fieldErrors.email}
        onChange={(event) => setValues((prev) => ({ ...prev, email: event.target.value }))}
      />
      <FormInputField
        ref={passwordRef}
        label="Password"
        type="password"
        name="password"
        autoComplete="new-password"
        value={values.password}
        error={fieldErrors.password}
        onChange={(event) => setValues((prev) => ({ ...prev, password: event.target.value }))}
      />
      {submit.phase === 'error' && !hasFieldErrors && (
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
