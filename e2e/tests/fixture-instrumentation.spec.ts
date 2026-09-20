import { expect, test } from '../fixtures/test'
import { FRONTEND_BASE_URL } from '../helpers/config'
import {
  createRecorderQueryClient,
  pollForExactlyOneEnvelope,
} from '../helpers/recorder-client'

const OPERATION = 'built_in_page_fixture_get'

function createEnvelope(): string {
  const event = {
    environment: 'production',
    tags: {
      service: 'wren-web',
      'api.operation': OPERATION,
      'api.failure_kind': 'upstream',
    },
    contexts: { report: { method: 'GET', status: 500 } },
    exception: { values: [{ value: '[Redacted exception]' }] },
  }
  return [
    JSON.stringify({ event_id: 'built-in-page-fixture-event' }),
    JSON.stringify({ type: 'event' }),
    JSON.stringify(event),
    '',
  ].join('\n')
}

test.describe('standard Playwright fixture instrumentation', () => {
  test('adds recorder identity and captures sensitive request values for page', async ({
    page,
    recorderIdentity,
    sensitiveValueRegistry,
  }) => {
    const cookieValue = `built-in-page-${recorderIdentity.queryIdentity}`
    const authorizationValue = `Bearer ${recorderIdentity.queryIdentity}`
    await page.context().addCookies([{
      name: 'fixture-cookie',
      value: cookieValue,
      url: FRONTEND_BASE_URL,
    }])
    await page.goto('/')

    const receivedAfterIso = new Date().toISOString()
    const responseStatus = await page.evaluate(async ({ envelope, authorization }) => {
      const response = await fetch('/_e2e/sentry/api/1/envelope/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-sentry-envelope',
          Authorization: authorization,
        },
        body: envelope,
      })
      return response.status
    }, { envelope: createEnvelope(), authorization: authorizationValue })

    expect(responseStatus).toBe(200)
    const sensitiveValues = sensitiveValueRegistry.snapshot()
    expect(sensitiveValues['session-cookie']).toContain(`fixture-cookie=${cookieValue}`)
    expect(sensitiveValues['authorization-header']).toContain(authorizationValue)

    const record = await pollForExactlyOneEnvelope(
      createRecorderQueryClient({ queryIdentity: recorderIdentity.queryIdentity }),
      OPERATION,
      'upstream',
      receivedAfterIso,
    )
    expect(record.queryIdentity).toBe(recorderIdentity.queryIdentity)
    expect(record.status).toBe(500)
  })
})
