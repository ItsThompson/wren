import { useState } from 'react'
import { Navigate, useSearchParams } from 'react-router'

import { useAuth } from '@/auth'
import { LoginForm } from './components/LoginForm'
import { RegisterForm } from './components/RegisterForm'

type AuthMode = 'login' | 'register'

/**
 * Register / login screen. Toggles between the two forms and, once the session
 * resolves to authenticated, redirects home. The initial form honors a `mode`
 * URL intent (`/auth?mode=register`), so the landing CTA can open signup
 * directly; it stays a controlled toggle afterwards.
 */
export function AuthView() {
  const { status } = useAuth()
  const [searchParams] = useSearchParams()
  const [mode, setMode] = useState<AuthMode>(
    searchParams.get('mode') === 'register' ? 'register' : 'login',
  )

  if (status === 'authenticated') {
    return <Navigate to="/" replace />
  }

  const isLogin = mode === 'login'
  return (
    <section className="reading-width max-w-[26rem] py-16">
      <h1 className="display-xl mb-8 text-foreground">{isLogin ? 'Welcome back' : 'Join Wren'}</h1>
      {isLogin ? <LoginForm /> : <RegisterForm />}
      <p className="mt-6 text-sm text-muted-foreground">
        {isLogin ? 'New to Wren?' : 'Already have an account?'}{' '}
        <button
          type="button"
          onClick={() => setMode(isLogin ? 'register' : 'login')}
          className="font-medium text-primary underline-offset-4 hover:underline"
        >
          {isLogin ? 'Create an account' : 'Log in'}
        </button>
      </p>
    </section>
  )
}
