import { type APIRequest, type APIRequestContext, expect } from '@playwright/test'

import { API_BASE_URL } from './config'
import type { NextResult, ProgressSnapshot } from './types'
import type { TestUser } from './users'

/**
 * The APIRequestContext seeding helper (spec section 13). Each function is one
 * external-app (`:8000`) call, mirroring the backend spine fixture, so the
 * Playwright suite drives the study spine against the live containerized stack
 * without re-implementing business rules. A registered context's cookie jar
 * carries the session across its subsequent calls.
 */

/**
 * A minimal publishable roadmap: two sequenced subsections (arrays -> hashing),
 * each with a resource and checklist items, a complete `suggested_path`, and
 * public visibility so a second user can follow it. Rebuilt per create so tests
 * never share a mutable literal.
 */
export function buildPublishableRoadmap() {
  return {
    title: 'Grokking DSA',
    visibility: 'public',
    suggested_path: ['sub_arrays', 'sub_hashing'],
    sections: [
      {
        title: 'Foundations',
        subsections: [
          {
            proposed_id: 'sub_arrays',
            title: 'Arrays',
            resources: [{ title: 'Guide', url: 'https://x.test', type: 'article' }],
            checklist_items: [
              { proposed_id: 'chk_read', text: 'Read it' },
              { proposed_id: 'chk_drill', text: 'Drill it' },
            ],
          },
          {
            proposed_id: 'sub_hashing',
            title: 'Hashing',
            prereq_ids: ['sub_arrays'],
            resources: [{ title: 'Vid', url: 'https://y.test', type: 'video' }],
            checklist_items: [{ proposed_id: 'chk_hash', text: 'Implement a counter' }],
          },
        ],
      },
    ],
  }
}

/** Every checklist item in the fixture above, in path order. */
export const SPINE_ITEM_IDS = ['chk_read', 'chk_drill', 'chk_hash']

/** Register `user` in a fresh API context; its cookie jar carries the session. */
export async function createAuthedContext(
  request: APIRequest,
  user: TestUser,
): Promise<APIRequestContext> {
  const context = await request.newContext({ baseURL: API_BASE_URL })
  const response = await context.post('/auth/register', { data: user })
  expect(response.status(), await response.text()).toBe(201)
  return context
}

export async function createPublishableRoadmap(context: APIRequestContext): Promise<string> {
  const response = await context.post('/roadmaps', { data: buildPublishableRoadmap() })
  expect(response.status(), await response.text()).toBe(201)
  const body = (await response.json()) as { id: string }
  return body.id
}

export async function publishRoadmap(context: APIRequestContext, id: string): Promise<void> {
  const response = await context.post(`/roadmaps/${id}:publish`)
  expect(response.status(), await response.text()).toBe(200)
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
