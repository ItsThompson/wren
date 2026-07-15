import { expect, test } from '@playwright/test'

import {
  SPINE_ITEM_IDS,
  completeItems,
  createAuthedContext,
  createPublishableRoadmap,
  followRoadmap,
  getNext,
  getProgress,
  publishRoadmap,
} from '../helpers/api'
import { uniqueUser } from '../helpers/users'

/**
 * The study spine over the live stack: register -> create -> publish -> follow
 * -> track. Seeded via the APIRequestContext helper; each test mints its own
 * unique users.
 */
test.describe('study spine (register -> create -> publish -> follow -> track)', () => {
  test('a follower can study a published roadmap end to end', async ({ playwright }) => {
    // register + create + publish (author)
    const author = await createAuthedContext(playwright.request, uniqueUser('author'))
    const roadmapId = await createPublishableRoadmap(author)
    await publishRoadmap(author, roadmapId)

    // follow (a distinct, unique follower)
    const follower = await createAuthedContext(playwright.request, uniqueUser('follower'))
    await followRoadmap(follower, roadmapId)

    // next starts at the first subsection's items, in path order
    const firstNext = await getNext(follower, roadmapId)
    expect(firstNext.items.map((item) => item.item_id)).toEqual(['chk_read', 'chk_drill'])
    expect(firstNext.complete).toBe(false)
    expect(firstNext.remaining_in_path).toBe(2)

    // track: complete everything -> progress is 100% and next reports done
    await completeItems(follower, roadmapId, SPINE_ITEM_IDS)
    const snapshot = await getProgress(follower, roadmapId)
    expect(snapshot.percent).toBe(100)
    expect(snapshot.checked_items).toBe(SPINE_ITEM_IDS.length)
    expect([...snapshot.checked_ids].sort()).toEqual([...SPINE_ITEM_IDS].sort())
    expect((await getNext(follower, roadmapId)).complete).toBe(true)

    await author.dispose()
    await follower.dispose()
  })

  test('a second follower has independent, empty progress (per-user scoping)', async ({
    playwright,
  }) => {
    const author = await createAuthedContext(playwright.request, uniqueUser('author'))
    const roadmapId = await createPublishableRoadmap(author)
    await publishRoadmap(author, roadmapId)

    const follower = await createAuthedContext(playwright.request, uniqueUser('follower'))
    await followRoadmap(follower, roadmapId)
    await completeItems(follower, roadmapId, SPINE_ITEM_IDS)

    const other = await createAuthedContext(playwright.request, uniqueUser('other'))
    await followRoadmap(other, roadmapId)
    const otherProgress = await getProgress(other, roadmapId)
    expect(otherProgress.checked_items).toBe(0)
    expect(otherProgress.checked_ids).toEqual([])

    await author.dispose()
    await follower.dispose()
    await other.dispose()
  })
})
