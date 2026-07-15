import { useState } from 'react'

import { LoginForm } from '@/views/AuthView/components/LoginForm'
import { RegisterForm } from '@/views/AuthView/components/RegisterForm'

interface ConsentLoginProps {
  clientName: string
}

/**
 * The login-first gate of the consent flow (section 08: "prompt login if there
 * is no session, then return to the decision"). Reuses the canonical auth forms
 * so the login/register logic is not duplicated, wrapped in consent-specific
 * framing. On success the `AuthProvider` flips to authenticated and the parent
 * `ConsentView` re-renders straight into the decision, keeping the human on this
 * page the whole time (no context-losing detour to the auth route).
 */
export function ConsentLogin({ clientName }: ConsentLoginProps) {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const isLogin = mode === 'login'

  return (
    <section className="reading-width max-w-[28rem] py-16">
      <div className="rounded-lg border border-border bg-card p-6 sm:p-8">
        <h1 className="display-m text-foreground">Log in to continue</h1>
        <p className="mt-3 text-sm text-muted-foreground">
          Log in to your Wren account to let{' '}
          <span className="font-semibold text-foreground">{clientName}</span> connect.
        </p>

        <div className="mt-6">{isLogin ? <LoginForm /> : <RegisterForm />}</div>

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
      </div>
    </section>
  )
}
