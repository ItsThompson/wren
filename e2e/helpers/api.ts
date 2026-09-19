import { createHash, randomBytes } from 'node:crypto'

import { type APIRequest, type APIRequestContext, expect } from '@playwright/test'

import { API_BASE_URL, MCP_BASE_URL } from './config'
import type { ContextOwner } from '../fixtures/context-owner'
import { ownDisposable } from '../fixtures/context-owner'
import type { OAuthFixtureIdentity, RoadmapFixtureIdentity } from '../fixtures/attempt-identity'
import type { NextResult, ProgressSnapshot } from './types'
import type { TestUser } from './users'

/**
 * The APIRequestContext seeding helper. Each function is one
 * external-app (`:8000`) call, mirroring the backend spine fixture, so the
 * Playwright suite drives the study spine against the live containerized stack
 * without re-implementing business rules. A registered context's cookie jar
 * carries the session across its subsequent calls.
 */

/** Optional fixture tags and publication setting. */
export interface PublishableRoadmapOptions {
  identity: RoadmapFixtureIdentity
  arrays?: string[]
  hashing?: string[]
  publishedVisibility?: 'public' | 'private'
}

/**
 * A minimal publishable roadmap: two sequenced subsections (arrays -> hashing),
 * each with a resource and checklist items and a complete `suggested_path`.
 * Publication access is omitted by default so the API default is exercised.
 * Rebuilt per create so tests never share a mutable literal.
 */
export function buildPublishableRoadmap(options: PublishableRoadmapOptions) {
  const subsectionIds = {
    arrays: `sub_${options.identity.proposedIdPrefix}-arrays`,
    hashing: `sub_${options.identity.proposedIdPrefix}-hashing`,
  }
  const roadmap = {
    title: options.identity.title,
    suggested_path: [subsectionIds.arrays, subsectionIds.hashing],
    sections: [
      {
        title: 'Foundations',
        subsections: [
          {
            proposed_id: subsectionIds.arrays,
            title: 'Arrays',
            tags: options.arrays ?? [],
            resources: [{ title: 'Guide', url: 'https://x.test', type: 'article' }],
            checklist_items: [
              { proposed_id: options.identity.itemIds[0], text: 'Read it' },
              { proposed_id: options.identity.itemIds[1], text: 'Drill it' },
            ],
          },
          {
            proposed_id: subsectionIds.hashing,
            title: 'Hashing',
            tags: options.hashing ?? [],
            prereq_ids: [subsectionIds.arrays],
            resources: [{ title: 'Vid', url: 'https://y.test', type: 'video' }],
            checklist_items: [{ proposed_id: options.identity.itemIds[2], text: 'Implement a counter' }],
          },
        ],
      },
    ],
  }
  if (options.publishedVisibility === undefined) return roadmap
  return { ...roadmap, published_visibility: options.publishedVisibility }
}

/** Register `user` in a fresh API context; its cookie jar carries the session. */
export async function createAuthedContext(
  request: APIRequest,
  user: TestUser,
  owner: ContextOwner,
): Promise<APIRequestContext> {
  const context = await request.newContext({ baseURL: API_BASE_URL })
  ownDisposable(owner, context, `api-account-${user.username}`)
  const response = await context.post('/auth/register', { data: user })
  expect(response.status(), await response.text()).toBe(201)
  return context
}

export async function createPublishableRoadmap(
  context: APIRequestContext,
  identity: RoadmapFixtureIdentity,
  options: Omit<PublishableRoadmapOptions, 'identity'> = {},
): Promise<string> {
  const response = await context.post(`${API_BASE_URL}/roadmaps`, {
    data: buildPublishableRoadmap({ ...options, identity }),
  })
  expect(response.status(), await response.text()).toBe(201)
  const body = (await response.json()) as { id: string }
  return body.id
}

export async function publishRoadmap(context: APIRequestContext, id: string): Promise<void> {
  const response = await context.post(`${API_BASE_URL}/roadmaps/${id}:publish`)
  expect(response.status(), await response.text()).toBe(200)
}

export async function forkRoadmap(
  context: APIRequestContext,
  id: string,
): Promise<Record<string, unknown>> {
  const response = await context.post(`/roadmaps/${id}:fork`)
  expect(response.status(), await response.text()).toBe(201)
  return (await response.json()) as Record<string, unknown>
}

export async function followRoadmap(context: APIRequestContext, id: string): Promise<void> {
  const response = await context.post(`/roadmaps/${id}/follow`)
  expect(response.status(), await response.text()).toBe(201)
}

export async function getNext(context: APIRequestContext, id: string): Promise<NextResult> {
  const response = await context.get(`/roadmaps/${id}/next`)
  expect(response.status(), await response.text()).toBe(200)
  return (await response.json()) as NextResult
}

export async function completeItems(
  context: APIRequestContext,
  id: string,
  itemIds: string[],
): Promise<void> {
  const response = await context.post(`/roadmaps/${id}/progress`, {
    data: { item_ids: itemIds, state: 'complete' },
  })
  expect(response.status(), await response.text()).toBe(200)
}

export async function getProgress(
  context: APIRequestContext,
  id: string,
): Promise<ProgressSnapshot> {
  const response = await context.get(`/roadmaps/${id}/progress`, { params: { detailed: true } })
  expect(response.status(), await response.text()).toBe(200)
  return (await response.json()) as ProgressSnapshot
}

export async function getRoadmap(context: APIRequestContext, id: string): Promise<Record<string, unknown>> {
  const response = await context.get(`/roadmaps/${id}`)
  expect(response.status(), await response.text()).toBe(200)
  return (await response.json()) as Record<string, unknown>
}

export async function getDashboard(context: APIRequestContext): Promise<Record<string, unknown>[]> {
  const response = await context.get('/me/dashboard')
  expect(response.status(), await response.text()).toBe(200)
  const body = (await response.json()) as { authored?: Record<string, unknown>[]; followed?: Record<string, unknown>[] }
  return [...(body.authored ?? []), ...(body.followed ?? [])]
}

export async function getProfile(
  context: APIRequestContext,
  handle: string,
): Promise<{ roadmaps?: Record<string, unknown>[] }> {
  const response = await context.get(`/users/${handle}`)
  expect(response.status(), await response.text()).toBe(200)
  return (await response.json()) as { roadmaps?: Record<string, unknown>[] }
}

export async function setPublishedVisibility(
  context: APIRequestContext,
  id: string,
  published_visibility: 'public' | 'private',
): Promise<void> {
  const response = await context.put(`/roadmaps/${id}/published-visibility`, { data: { published_visibility } })
  expect(response.status(), await response.text()).toBe(200)
}

export async function archiveRoadmap(context: APIRequestContext, id: string): Promise<void> {
  const response = await context.post(`/roadmaps/${id}:archive`)
  expect(response.status(), await response.text()).toBe(200)
}

export async function createAgentAccessToken(
  context: APIRequestContext,
  oauthIdentity: OAuthFixtureIdentity,
): Promise<string> {
  const { clientName, redirectUri, state } = oauthIdentity
  const verifier = randomBytes(32).toString('base64url')
  const challenge = createHash('sha256').update(verifier).digest('base64url')
  const registration = await context.post('/register', {
    data: { client_name: clientName, redirect_uris: [redirectUri], scope: 'roadmaps:read' },
  })
  expect(registration.status(), await registration.text()).toBe(201)
  const { client_id: clientId } = (await registration.json()) as { client_id: string }

  const authorization = await context.get('/authorize', {
    maxRedirects: 0,
    params: {
      client_id: clientId,
      redirect_uri: redirectUri,
      response_type: 'code',
      code_challenge: challenge,
      code_challenge_method: 'S256',
      scope: 'roadmaps:read',
      state,
      resource: MCP_BASE_URL,
    },
  })
  expect(authorization.status(), await authorization.text()).toBe(302)
  const consentLocation = authorization.headers().location
  expect(consentLocation).toBeTruthy()
  const authRequestId = new URL(consentLocation).searchParams.get('auth_request_id')
  expect(authRequestId).toBeTruthy()

  const consentContext = await context.get('/authorize/context', {
    params: { auth_request_id: authRequestId as string },
  })
  expect(consentContext.status(), await consentContext.text()).toBe(200)
  expect((await consentContext.json()).authenticated).toBe(true)

  const decision = await context.post('/authorize/decision', {
    data: { auth_request_id: authRequestId, approve: true },
  })
  expect(decision.status(), await decision.text()).toBe(200)
  const decisionLocation = (await decision.json()).redirect_uri as string
  const code = new URL(decisionLocation).searchParams.get('code')
  expect(code).toBeTruthy()

  const token = await context.post('/token', {
    form: {
      grant_type: 'authorization_code',
      client_id: clientId,
      code: code as string,
      code_verifier: verifier,
      redirect_uri: redirectUri,
      resource: MCP_BASE_URL,
    },
  })
  expect(token.status(), await token.text()).toBe(200)
  const body = (await token.json()) as { access_token: string }
  return body.access_token
}

export async function listMcpTools(
  context: APIRequestContext,
  accessToken: string,
): Promise<Record<string, unknown>[]> {
  const response = await context.post(`${MCP_BASE_URL}/mcp`, {
    headers: {
      Authorization: `Bearer ${accessToken}`,
      Accept: 'application/json, text/event-stream',
    },
    data: { jsonrpc: '2.0', id: 1, method: 'tools/list', params: {} },
  })
  expect(response.status(), await response.text()).toBe(200)
  const body = (await response.json()) as { result: { tools: Record<string, unknown>[] } }
  return body.result.tools
}

export async function callMcpTool(
  context: APIRequestContext,
  accessToken: string,
  name: string,
  arguments_: Record<string, unknown>,
): Promise<{ structuredContent: Record<string, unknown> }> {
  const response = await context.post(`${MCP_BASE_URL}/mcp`, {
    headers: {
      Authorization: `Bearer ${accessToken}`,
      Accept: 'application/json, text/event-stream',
    },
    data: {
      jsonrpc: '2.0',
      id: 2,
      method: 'tools/call',
      params: { name, arguments: arguments_ },
    },
  })
  expect(response.status(), await response.text()).toBe(200)
  const body = (await response.json()) as { result: { structuredContent: Record<string, unknown> } }
  return body.result
}
