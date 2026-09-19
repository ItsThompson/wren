import type { APIRequest } from '@playwright/test'

import { API_BASE_URL, RECORDER_CONTROL_TOKEN } from '../helpers/config'
import type { BrowserFailureKind, EnvelopeRecord } from '../recorder/src/types'
import type { RecorderFixtureIdentity } from './attempt-identity'
import type { AsyncResource, ContextOwner } from './context-owner'

export interface RecorderClient extends AsyncResource {
  queryIdentity: string
  query(
    operation: string,
    failureKind: BrowserFailureKind,
    receivedAfterIso: string,
  ): Promise<readonly EnvelopeRecord[]>
}

export async function createRecorderClient(
  request: APIRequest,
  owner: ContextOwner,
  identity: RecorderFixtureIdentity,
): Promise<RecorderClient> {
  const context = await request.newContext({ baseURL: API_BASE_URL })
  const client: RecorderClient = {
    name: `recorder-client-${identity.queryIdentity}`,
    queryIdentity: identity.queryIdentity,
    async query(operation, failureKind, receivedAfterIso) {
      const response = await context.get('/_e2e/recorder/envelopes', {
        headers: {
          'X-Recorder-Token': RECORDER_CONTROL_TOKEN,
          'X-Recorder-Query-Identity': identity.queryIdentity,
        },
        params: { operation, failureKind, receivedAfterIso },
      })
      if (!response.ok()) throw new Error(`recorder query failed with status ${response.status()}`)
      const body = (await response.json()) as { records: EnvelopeRecord[] }
      return body.records
    },
    close: () => context.dispose(),
  }
  owner.own(client)
  return client
}
