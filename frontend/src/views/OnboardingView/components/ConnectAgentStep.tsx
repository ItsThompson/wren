import { Link } from 'react-router'

import type { ConnectAgentStepProps } from '../types'
import { StepControls } from './StepControls'

/**
 * The Connect-an-agent step. Presentational: it mirrors the docs Getting Started
 * guide (add Wren's MCP server to your client, authorize it through Wren's OAuth
 * consent, then confirm the agent on the Connected agents surface) and displays
 * the MCP URL from its `mcpUrl` prop. It reads no env and hardcodes no routes:
 * `mcpUrl`, `connectionsHref`, and `docsHref` are threaded from the view root.
 * Nothing here is required to advance; Continue and Skip both move on.
 */
export function ConnectAgentStep({
  onContinue,
  onBack,
  onSkip,
  isFirstStep,
  isLastStep,
  isSubmitting,
  error,
  mcpUrl,
  connectionsHref,
  docsHref,
}: ConnectAgentStepProps) {
  return (
    <div className="flex flex-col">
      <p className="text-sm font-medium text-muted-foreground">Connect an agent</p>
      <h1 className="display-l mt-3 text-foreground">Let an agent author for you</h1>
      <p className="mt-4 max-w-[52ch] text-muted-foreground">
        Roadmaps are authored by an AI agent running in your own MCP client (for example Claude
        Desktop or Cursor). Add Wren&rsquo;s MCP server to that client to let it author roadmaps for
        you.
      </p>

      <div className="mt-6">
        <p className="text-sm font-medium text-foreground">Wren&rsquo;s MCP server URL</p>
        <code className="mt-2 block rounded-md bg-secondary px-3 py-2 font-mono text-sm text-secondary-foreground">
          {mcpUrl}
        </code>
      </div>

      <p className="mt-6 max-w-[52ch] text-muted-foreground">
        The first time your client connects, Wren asks you to sign in and approve access on an OAuth
        consent screen: there are no API keys to copy or paste. Once you approve, the authorized
        agent appears on your{' '}
        <Link to={connectionsHref} className="text-primary underline-offset-4 hover:underline">
          Connected agents
        </Link>{' '}
        page, ready to author roadmaps for you.
      </p>

      <p className="mt-4 text-sm text-muted-foreground">
        Need the full walkthrough? See the{' '}
        <a
          href={docsHref}
          target="_blank"
          rel="noreferrer"
          className="text-primary underline-offset-4 hover:underline"
        >
          Getting Started guide
        </a>
        .
      </p>

      <StepControls
        onContinue={onContinue}
        onBack={onBack}
        onSkip={onSkip}
        isFirstStep={isFirstStep}
        isLastStep={isLastStep}
        isSubmitting={isSubmitting}
        error={error}
        continueLabel="Continue"
      />
    </div>
  )
}
