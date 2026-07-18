import type { ReactNode } from 'react'

import { ConnectAgentStep } from './components/ConnectAgentStep'
import { HowItWorksStep } from './components/HowItWorksStep'
import { OnboardingProgress } from './components/OnboardingProgress'
import { WelcomeStep } from './components/WelcomeStep'
import { useOnboarding } from './hooks/useOnboarding'
import { STEPS } from './steps'
import { OnboardingStepId, type ConnectAgentStepProps, type OnboardingStepProps } from './types'

/**
 * Pinned public MCP base URL, used when the build-time `VITE_MCP_BASE_URL` is not
 * set (local `npm run dev`, tests). Production bakes the env from `MCP_PUBLIC_URL`
 * via the Dockerfile ARG + compose build.args.
 */
const DEFAULT_MCP_BASE_URL = 'https://mcp.usewren.com'

/**
 * Config for the connect-agent step, sourced once here at the view root and
 * threaded down as props so no leaf reads `import.meta.env` or hardcodes routes.
 * Mirrors `App.tsx`'s read-once handling of `VITE_API_BASE_URL`. `/mcp` is the
 * MCP transport path appended to the origin.
 */
const MCP_URL = `${import.meta.env.VITE_MCP_BASE_URL ?? DEFAULT_MCP_BASE_URL}/mcp`
const CONNECTIONS_HREF = '/settings/connections'
const DOCS_GETTING_STARTED_HREF = 'https://docs.usewren.com/getting-started'

/** Exhaustiveness guard: a compile error here means a step `id` has no case. */
function assertNever(value: never): never {
  throw new Error(`Unhandled onboarding step: ${String(value)}`)
}

/**
 * OnboardingView: the thin orchestrator. It composes the state-machine hook with
 * the progress indicator and the active step, and renders a chrome-free
 * full-viewport frame (it lives outside `AppShell`, so there is no TopBar or page
 * gutter). All state and the completion call live in {@link useOnboarding}; steps
 * receive callbacks + flags and emit intent only.
 *
 * The active step routes on the step's `id` (a switch, so each concrete step can
 * receive its own props: ConnectAgentStep additionally gets its display config).
 * `onContinue` maps to the completion path on the last step and to `next`
 * otherwise, so the same shared props drive every step.
 */
export function OnboardingView() {
  const { state, actions } = useOnboarding()
  const step = STEPS[state.stepIndex]

  const stepProps: OnboardingStepProps = {
    onContinue: state.isLastStep ? actions.submit : actions.next,
    onBack: actions.back,
    onSkip: actions.skip,
    isFirstStep: state.isFirstStep,
    isLastStep: state.isLastStep,
    isSubmitting: state.phase === 'submitting',
    error: state.error,
  }

  let activeStep: ReactNode
  switch (step.id) {
    case OnboardingStepId.WELCOME:
      activeStep = <WelcomeStep {...stepProps} />
      break
    case OnboardingStepId.CONNECT_AGENT: {
      const connectAgentProps: ConnectAgentStepProps = {
        ...stepProps,
        mcpUrl: MCP_URL,
        connectionsHref: CONNECTIONS_HREF,
        docsHref: DOCS_GETTING_STARTED_HREF,
      }
      activeStep = <ConnectAgentStep {...connectAgentProps} />
      break
    }
    case OnboardingStepId.HOW_IT_WORKS:
      activeStep = <HowItWorksStep {...stepProps} />
      break
    default:
      activeStep = assertNever(step.id)
  }

  return (
    <main className="flex min-h-screen flex-col bg-background px-5 py-10">
      <div className="mx-auto flex w-full max-w-[32rem] flex-1 flex-col justify-center">
        <OnboardingProgress stepIndex={state.stepIndex} stepCount={state.stepCount} />
        <div className="mt-10">{activeStep}</div>
      </div>
    </main>
  )
}
