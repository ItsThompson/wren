import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll } from 'vitest'
import { Route, Routes, useLocation, useNavigate } from 'react-router'

import { renderWithProviders } from '@/test/renderWithProviders'
import { colorForTag } from '@/lib/tag-color'
import type { ProgressSnapshot, ProgressUpdateResult, Roadmap } from './types'
import { RoadmapView } from './RoadmapView'

const BASE = 'https://api.test'
const ROADMAP_ID = 'grokking-dsa-7f3k'

/** The signed-in user; `id` matches `buildDraft`'s owner so ownership resolves. */
const AUTH_USER = {
  id: 'user-1',
  username: 'ada',
  email: 'ada@example.com',
  created_at: '2026-07-15T00:00:00Z',
}

/** A minimal owned draft in the OpenAPI-generated `Roadmap` shape. */
function buildDraft(overrides: Partial<Roadmap> = {}): Roadmap {
  return {
    id: ROADMAP_ID,
    owner: 'user-1',
    title: 'Grokking DSA',
    description: 'A prerequisite-aware path.',
    subject_tags: ['computer-science'],
    visibility: 'private',
    status: 'draft',
    revision: 1,
    section_order: ['sec_foundations'],
    suggested_path: ['sub_hashing', 'sub_arrays'],
    sections: {
      sec_foundations: {
        id: 'sec_foundations',
        title: 'Foundations',
        subsection_order: ['sub_arrays', 'sub_hashing'],
        subsections: {
          sub_arrays: {
            id: 'sub_arrays',
            title: 'Arrays & two pointers',
            description: 'Start here.',
            tags: ['arrays'],
            effort_estimate: '3h',
            prereq_ids: [],
            resource_order: ['res_guide'],
            resources: {
              res_guide: {
                id: 'res_guide',
                title: 'Two-pointer guide',
                url: 'https://example.com/tp',
                type: 'article',
              },
            },
            item_order: ['chk_read'],
            checklist_items: { chk_read: { id: 'chk_read', text: 'Read the walkthrough' } },
          },
          sub_hashing: {
            id: 'sub_hashing',
            title: 'Hashing',
            tags: [],
            prereq_ids: ['sub_arrays'],
            resource_order: [],
            resources: {},
            item_order: ['chk_hash'],
            checklist_items: { chk_hash: { id: 'chk_hash', text: 'Implement a counter' } },
          },
        },
      },
    },
    created_at: '2026-07-15T00:00:00Z',
    updated_at: '2026-07-15T00:00:00Z',
    ...overrides,
  }
}

const server = setupServer(
  // Default "nothing next" so published-view tests that don't exercise the next
  // highlight don't trip `onUnhandledRequest: 'error'`; specific tests override
  // this via `server.use` (runtime handlers take precedence over initial ones).
  // `complete: false` keeps the calm all-caught-up banner off by default.
  http.get('*/roadmaps/:id/next', () =>
    HttpResponse.json({ items: [], remaining_in_path: 0, complete: false }),
  ),
)

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

/** A progress snapshot for the tracking view; the UI derives counts from ids. */
function buildProgress(checkedIds: string[] = []): ProgressSnapshot {
  return {
    roadmap_id: ROADMAP_ID,
    total_items: 2,
    checked_items: checkedIds.length,
    percent: 0,
    checked_ids: checkedIds,
  }
}

/** A progress_update result echoing the fresh checked set + a next suggestion. */
function buildUpdateResult(checkedIds: string[]): ProgressUpdateResult {
  return { progress: buildProgress(checkedIds), next: { items: [], remaining_in_path: 0, complete: false } }
}

/** Renders the current pathname so navigation (e.g. after a fork) is assertable. */
function LocationProbe() {
  const location = useLocation()
  return <div data-testid="location">{location.pathname}</div>
}

/**
 * A test-only control that navigates to another route without unmounting the
 * view under test, so a `:roadmapId` change on the SAME RoadmapView instance is
 * exercisable (the fork -> navigate / roadmap-to-roadmap case behind R2).
 */
function NavTo({ to, label }: { to: string; label: string }) {
  const navigate = useNavigate()
  return (
    <button type="button" onClick={() => navigate(to)}>
      {label}
    </button>
  )
}

function renderView(user: typeof AUTH_USER | null = AUTH_USER) {
  server.use(
    user
      ? http.post('*/auth/refresh', () => HttpResponse.json(user))
      : http.post('*/auth/refresh', () => new HttpResponse(null, { status: 401 })),
  )
  return renderWithProviders(
    <>
      <Routes>
        <Route path="/roadmaps/:roadmapId" element={<RoadmapView />} />
      </Routes>
      <LocationProbe />
    </>,
    { initialEntries: [`/roadmaps/${ROADMAP_ID}`], baseUrl: BASE, useRealAuth: true },
  )
}

/** Renders the view with a starting URL hash so anchor-scroll can be exercised. */
function renderViewAtHash(hash: string) {
  server.use(http.post('*/auth/refresh', () => HttpResponse.json(AUTH_USER)))
  return renderWithProviders(
    <>
      <Routes>
        <Route path="/roadmaps/:roadmapId" element={<RoadmapView />} />
      </Routes>
      <LocationProbe />
    </>,
    { initialEntries: [`/roadmaps/${ROADMAP_ID}${hash}`], baseUrl: BASE, useRealAuth: true },
  )
}

describe('RoadmapView', () => {
  it('renders an owned draft in preview mode, labeled as a draft', async () => {
    server.use(http.get('*/roadmaps/:id', () => HttpResponse.json(buildDraft())))
    renderView()

    expect(await screen.findByText('Grokking DSA')).toBeInTheDocument()
    // Visibly labeled as a draft preview.
    expect(screen.getByText(/draft · preview/i)).toBeInTheDocument()
    // Subject tag chip + section + subsection titles rendered.
    expect(screen.getByText('computer-science')).toBeInTheDocument()
    expect(screen.getByText('Foundations')).toBeInTheDocument()
    expect(screen.getByText('Arrays & two pointers')).toBeInTheDocument()
    // Resource as a real link.
    const link = screen.getByRole('link', { name: 'Two-pointer guide' })
    expect(link).toHaveAttribute('href', 'https://example.com/tp')
    // Checklist text is shown read-only.
    expect(screen.getByText('Read the walkthrough')).toBeInTheDocument()
  })

  it('is preview-only: no follow action and no interactive checkboxes', async () => {
    server.use(http.get('*/roadmaps/:id', () => HttpResponse.json(buildDraft())))
    renderView()
    await screen.findByText('Grokking DSA')

    expect(screen.queryByRole('button', { name: /follow/i })).not.toBeInTheDocument()
    // No checkbox inputs persist progress in a draft preview.
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
  })

  it('orders subsections by suggested_path, then structural fallback', async () => {
    server.use(http.get('*/roadmaps/:id', () => HttpResponse.json(buildDraft())))
    renderView()
    await screen.findByText('Grokking DSA')

    // suggested_path is [sub_hashing, sub_arrays], so Hashing renders first even
    // though subsection_order lists Arrays first.
    const headings = screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent)
    expect(headings).toEqual(['Hashing', 'Arrays & two pointers'])
  })

  it('shows a not-found state when the roadmap is unreachable (404)', async () => {
    server.use(
      http.get('*/roadmaps/:id', () =>
        HttpResponse.json(
          { type: 'x', title: 'Resource not found', status: 404, code: 'NOT_FOUND' },
          { status: 404, headers: { 'content-type': 'application/problem+json' } },
        ),
      ),
    )
    renderView()

    expect(await screen.findByText('Roadmap not found')).toBeInTheDocument()
    expect(
      screen.getByText(/does not exist or is not shared with you/i),
    ).toBeInTheDocument()
  })

  it('renders the same dedicated view for a 403 as a 404 (no existence leak)', async () => {
    server.use(
      http.get('*/roadmaps/:id', () =>
        HttpResponse.json(
          { type: 'x', title: 'Access forbidden', status: 403, code: 'FORBIDDEN' },
          { status: 403, headers: { 'content-type': 'application/problem+json' } },
        ),
      ),
    )
    renderView()

    // A 403 (someone else's private roadmap) must not read differently from a
    // 404, so the roadmap's existence never leaks.
    expect(await screen.findByText('Roadmap not found')).toBeInTheDocument()
    expect(
      screen.getByText(/does not exist or is not shared with you/i),
    ).toBeInTheDocument()
  })

  it('shows a loading skeleton before the roadmap resolves', () => {
    server.use(http.get('*/roadmaps/:id', () => HttpResponse.json(buildDraft())))
    renderView()
    expect(screen.getByLabelText('Loading roadmap')).toBeInTheDocument()
  })

  it('renders a bare subsection (no tags, resources, or description) without crashing', async () => {
    const bare = buildDraft({
      section_order: ['sec_only'],
      suggested_path: [],
      sections: {
        sec_only: {
          id: 'sec_only',
          title: 'Only section',
          subsection_order: ['sub_bare'],
          subsections: {
            sub_bare: {
              id: 'sub_bare',
              title: 'Bare node',
              tags: [],
              prereq_ids: [],
              resource_order: [],
              resources: {},
              item_order: ['chk_x'],
              checklist_items: { chk_x: { id: 'chk_x', text: 'Only item' } },
            },
          },
        },
      },
    })
    server.use(http.get('*/roadmaps/:id', () => HttpResponse.json(bare)))
    renderView()

    expect(await screen.findByText('Bare node')).toBeInTheDocument()
    expect(screen.getByText('Only item')).toBeInTheDocument()
    // No resource links exist for a resource-less node.
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })
})

describe('RoadmapView publish', () => {
  const PUBLISH_URL = `${BASE}/roadmaps/${ROADMAP_ID}:publish`

  it('offers a Publish action on an owned draft', async () => {
    server.use(http.get('*/roadmaps/:id', () => HttpResponse.json(buildDraft())))
    renderView()
    await screen.findByText('Grokking DSA')

    expect(screen.getByRole('button', { name: /^publish$/i })).toBeInTheDocument()
  })

  it('renders the returned violations inline when publish is hard-blocked (422)', async () => {
    const user = userEvent.setup()
    server.use(
      http.get('*/roadmaps/:id', () => HttpResponse.json(buildDraft())),
      http.post(PUBLISH_URL, () =>
        HttpResponse.json(
          {
            type: 'x',
            title: 'Draft cannot be published',
            status: 422,
            code: 'VALIDATION',
            violations: [
              {
                rule: 'V7_RESOURCE_REQUIRED',
                ids: ['sub_hashing'],
                message: 'subsection sub_hashing has no resources',
              },
            ],
          },
          { status: 422, headers: { 'content-type': 'application/problem+json' } },
        ),
      ),
    )
    renderView()
    await screen.findByText('Grokking DSA')

    await user.click(screen.getByRole('button', { name: /^publish$/i }))

    // The offending rule + message are surfaced inline for the author to fix.
    expect(await screen.findByText('subsection sub_hashing has no resources')).toBeInTheDocument()
    expect(screen.getByText('V7_RESOURCE_REQUIRED')).toBeInTheDocument()
    // Hard-block: the roadmap stays a draft.
    expect(screen.getByText(/draft · preview/i)).toBeInTheDocument()
  })

  it('routes to the tracking list view after a successful publish (200)', async () => {
    const user = userEvent.setup()
    server.use(
      http.get('*/roadmaps/:id', () => HttpResponse.json(buildDraft())),
      http.post(PUBLISH_URL, () => HttpResponse.json(buildDraft({ status: 'published' }))),
      http.get('*/roadmaps/:id/progress', () => HttpResponse.json(buildProgress())),
    )
    renderView()
    await screen.findByText('Grokking DSA')

    await user.click(screen.getByRole('button', { name: /^publish$/i }))

    // Publish is one-way: the tracking list view (progress bar + interactive
    // checklist) replaces the preview; the action and the draft badge are gone.
    expect(
      await screen.findByRole('progressbar', { name: /overall progress/i }),
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^publish$/i })).not.toBeInTheDocument()
    expect(screen.queryByText(/draft · preview/i)).not.toBeInTheDocument()
    expect(screen.getAllByRole('checkbox').length).toBeGreaterThan(0)
  })

  it('renders the tracking list view (not the preview) on a published roadmap', async () => {
    server.use(
      http.get('*/roadmaps/:id', () => HttpResponse.json(buildDraft({ status: 'published' }))),
      http.get('*/roadmaps/:id/progress', () => HttpResponse.json(buildProgress())),
    )
    renderView()

    expect(
      await screen.findByRole('progressbar', { name: /overall progress/i }),
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^publish$/i })).not.toBeInTheDocument()
    expect(screen.queryByText(/draft · preview/i)).not.toBeInTheDocument()
  })

  it('surfaces a retry message when publish fails unexpectedly (500)', async () => {
    const user = userEvent.setup()
    server.use(
      http.get('*/roadmaps/:id', () => HttpResponse.json(buildDraft())),
      http.post(PUBLISH_URL, () => new HttpResponse(null, { status: 500 })),
    )
    renderView()
    await screen.findByText('Grokking DSA')

    await user.click(screen.getByRole('button', { name: /^publish$/i }))

    expect(await screen.findByText(/couldn.t publish this roadmap/i)).toBeInTheDocument()
    // Still a draft, and the action remains available to retry.
    expect(screen.getByRole('button', { name: /^publish$/i })).toBeInTheDocument()
  })
})

describe('RoadmapView progress tracking', () => {
  const PROGRESS_URL = `${BASE}/roadmaps/${ROADMAP_ID}/progress`

  function publishedRoadmap() {
    // suggested_path [sub_hashing, sub_arrays]; one item each (2 items total).
    return buildDraft({ status: 'published' })
  }

  it('renders interactive checkboxes and roadmap + section bars, but no per-item bars', async () => {
    server.use(
      http.get('*/roadmaps/:id', () => HttpResponse.json(publishedRoadmap())),
      http.get(PROGRESS_URL, () => HttpResponse.json(buildProgress())),
    )
    renderView()

    // Checklist items are interactive checkboxes (both subsections' items).
    expect(
      await screen.findByRole('checkbox', { name: 'Read the walkthrough' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: 'Implement a counter' })).toBeInTheDocument()
    // Bars only at roadmap (1) + section (1) level: never per subsection/item.
    expect(screen.getAllByRole('progressbar')).toHaveLength(2)
  })

  it('persists a check via progress_update and advances the overall bar', async () => {
    const user = userEvent.setup()
    let posted: unknown
    server.use(
      http.get('*/roadmaps/:id', () => HttpResponse.json(publishedRoadmap())),
      http.get(PROGRESS_URL, () => HttpResponse.json(buildProgress())),
      http.post(PROGRESS_URL, async ({ request }) => {
        posted = await request.json()
        return HttpResponse.json(buildUpdateResult(['chk_read']))
      }),
    )
    renderView()

    const overall = await screen.findByRole('progressbar', { name: /overall progress/i })
    expect(overall).toHaveAttribute('aria-valuenow', '0')

    await user.click(screen.getByRole('checkbox', { name: 'Read the walkthrough' }))

    // Explicit-set complete for exactly the toggled item.
    await waitFor(() =>
      expect(posted).toEqual({ item_ids: ['chk_read'], state: 'complete' }),
    )
    // One of two items checked -> overall bar reads 50%.
    await waitFor(() =>
      expect(
        screen.getByRole('progressbar', { name: /overall progress/i }),
      ).toHaveAttribute('aria-valuenow', '50'),
    )
  })

  it('sends state=incomplete when unchecking an already-checked item', async () => {
    const user = userEvent.setup()
    let posted: unknown
    server.use(
      http.get('*/roadmaps/:id', () => HttpResponse.json(publishedRoadmap())),
      http.get(PROGRESS_URL, () => HttpResponse.json(buildProgress(['chk_read']))),
      http.post(PROGRESS_URL, async ({ request }) => {
        posted = await request.json()
        return HttpResponse.json(buildUpdateResult([]))
      }),
    )
    renderView()

    const checkbox = await screen.findByRole('checkbox', { name: 'Read the walkthrough' })
    // The detailed snapshot hydrates the checked state asynchronously on mount.
    await waitFor(() => expect(checkbox).toBeChecked())
    await user.click(checkbox)

    await waitFor(() =>
      expect(posted).toEqual({ item_ids: ['chk_read'], state: 'incomplete' }),
    )
  })

  it('derives subsection done-state (olive check) when all its items are checked', async () => {
    server.use(
      http.get('*/roadmaps/:id', () => HttpResponse.json(publishedRoadmap())),
      // sub_arrays has one item (chk_read); checking it marks the subsection done.
      http.get(PROGRESS_URL, () => HttpResponse.json(buildProgress(['chk_read']))),
    )
    renderView()

    // The done label appears once (for sub_arrays), not for the unfinished node.
    expect(await screen.findAllByText('done')).toHaveLength(1)
  })
})

describe('RoadmapView deadline countdown', () => {
  const PROGRESS_URL = `${BASE}/roadmaps/${ROADMAP_ID}/progress`
  const DEADLINE_URL = `${BASE}/roadmaps/${ROADMAP_ID}/deadline`

  /** A progress snapshot carrying (or clearing) the per-user deadline. */
  function progressWithDeadline(deadline: string | null): ProgressSnapshot {
    return { ...buildProgress(), deadline: deadline ?? undefined }
  }

  /** The `Progress` record the PUT /deadline endpoint echoes back. */
  function progressRecord(deadline: string | null) {
    return {
      user_id: 'user-1',
      roadmap_id: ROADMAP_ID,
      deadline,
      checked: {},
      updated_at: '2026-07-15T00:00:00Z',
    }
  }

  it('shows the deadline date and a countdown when one is set', async () => {
    server.use(
      http.get('*/roadmaps/:id', () => HttpResponse.json(buildDraft({ status: 'published' }))),
      http.get(PROGRESS_URL, () => HttpResponse.json(progressWithDeadline('2099-12-31'))),
    )
    renderView()

    const input = await screen.findByLabelText('Deadline')
    // The detailed snapshot hydrates the deadline asynchronously on mount.
    await waitFor(() => expect(input).toHaveValue('2099-12-31'))
    // A countdown renders (its exact label is covered by deadline-countdown.test).
    expect(screen.getByTestId('deadline-countdown')).toBeInTheDocument()
  })

  it('sets a deadline via PUT when the date input changes', async () => {
    const user = userEvent.setup()
    let put: unknown
    server.use(
      http.get('*/roadmaps/:id', () => HttpResponse.json(buildDraft({ status: 'published' }))),
      http.get(PROGRESS_URL, () => HttpResponse.json(progressWithDeadline(null))),
      http.put(DEADLINE_URL, async ({ request }) => {
        put = await request.json()
        return HttpResponse.json(progressRecord('2026-12-01'))
      }),
    )
    renderView()

    const input = await screen.findByLabelText('Deadline')
    await user.type(input, '2026-12-01')

    await waitFor(() => expect(put).toEqual({ deadline: '2026-12-01' }))
    await waitFor(() => expect(input).toHaveValue('2026-12-01'))
  })

  it('clears the deadline via PUT null when Clear is pressed', async () => {
    const user = userEvent.setup()
    let put: unknown
    server.use(
      http.get('*/roadmaps/:id', () => HttpResponse.json(buildDraft({ status: 'published' }))),
      http.get(PROGRESS_URL, () => HttpResponse.json(progressWithDeadline('2099-12-31'))),
      http.put(DEADLINE_URL, async ({ request }) => {
        put = await request.json()
        return HttpResponse.json(progressRecord(null))
      }),
    )
    renderView()

    // Clear only appears once a deadline has hydrated.
    await waitFor(() => expect(screen.getByLabelText('Deadline')).toHaveValue('2099-12-31'))
    await user.click(screen.getByRole('button', { name: /clear/i }))

    await waitFor(() => expect(put).toEqual({ deadline: null }))
    await waitFor(() => expect(screen.getByLabelText('Deadline')).toHaveValue(''))
  })

  it('reverts an optimistic deadline set when the PUT errors at the network level', async () => {
    server.use(
      http.get('*/roadmaps/:id', () => HttpResponse.json(buildDraft({ status: 'published' }))),
      http.get(PROGRESS_URL, () => HttpResponse.json(progressWithDeadline(null))),
      http.put(DEADLINE_URL, () => HttpResponse.error()),
    )
    renderView()

    const input = await screen.findByLabelText('Deadline')
    // D4 date-input exception: this site keeps fireEvent.change. user.type awaits
    // its act() flush, which lets the network-error revert land before the
    // synchronous optimistic assertion below can observe the value.
    fireEvent.change(input, { target: { value: '2026-12-01' } })
    // Optimistically shows the new date synchronously ...
    expect(input).toHaveValue('2026-12-01')
    // ... then reverts to the prior (empty) value when the write throws.
    await waitFor(() => expect(input).toHaveValue(''))
  })

  it('surfaces a quiet inline notice and reverts when a deadline write fails (500)', async () => {
    const user = userEvent.setup()
    server.use(
      http.get('*/roadmaps/:id', () => HttpResponse.json(buildDraft({ status: 'published' }))),
      http.get(PROGRESS_URL, () => HttpResponse.json(progressWithDeadline(null))),
      http.put(DEADLINE_URL, () => new HttpResponse(null, { status: 500 })),
    )
    renderView()

    const input = await screen.findByLabelText('Deadline')
    await user.type(input, '2026-12-01')

    // The deadline write path now announces failures like the toggle path does ...
    expect(await screen.findByRole('status')).toHaveTextContent(/couldn.t save that change/i)
    // ... and the optimistic date is rolled back.
    await waitFor(() => expect(input).toHaveValue(''))
  })

  it('surfaces the ochre re-read prompt when a deadline write is stale (409)', async () => {
    const user = userEvent.setup()
    server.use(
      http.get('*/roadmaps/:id', () => HttpResponse.json(buildDraft({ status: 'published' }))),
      http.get(PROGRESS_URL, () => HttpResponse.json(progressWithDeadline(null))),
      http.put(DEADLINE_URL, () =>
        HttpResponse.json(
          { type: 'x', title: 'Conflict', status: 409, code: 'STALE_REVISION', detail: 're-read' },
          { status: 409, headers: { 'content-type': 'application/problem+json' } },
        ),
      ),
    )
    renderView()

    const input = await screen.findByLabelText('Deadline')
    await user.type(input, '2026-12-01')

    expect(await screen.findByRole('alert')).toHaveTextContent(/reload to continue/i)
    await waitFor(() => expect(input).toHaveValue(''))
  })
})

describe('RoadmapView fork', () => {
  const FORK_URL = `${BASE}/roadmaps/${ROADMAP_ID}:fork`
  const OTHER_USER = {
    id: 'user-2',
    username: 'grace',
    email: 'grace@example.com',
    created_at: '2026-07-15T00:00:00Z',
  }

  it('forks an owned draft and navigates to the new draft', async () => {
    const user = userEvent.setup()
    server.use(
      // Any id resolves to a draft (the source, then the fork after navigation).
      http.get('*/roadmaps/:id', ({ params }) =>
        HttpResponse.json(buildDraft({ id: String(params.id) })),
      ),
      http.post(FORK_URL, () =>
        HttpResponse.json(buildDraft({ id: 'grokking-dsa-9x2b' }), { status: 201 }),
      ),
    )
    renderView()
    await screen.findByText('Grokking DSA')

    await user.click(screen.getByRole('button', { name: /^fork$/i }))

    // Fork navigates to the freshly-minted draft's route.
    await waitFor(() =>
      expect(screen.getByTestId('location')).toHaveTextContent('/roadmaps/grokking-dsa-9x2b'),
    )
  })

  it('offers Fork but not Edit details to a non-owner on a published roadmap', async () => {
    server.use(
      http.get('*/roadmaps/:id', () =>
        HttpResponse.json(buildDraft({ status: 'published', owner: 'user-1' })),
      ),
      http.get('*/roadmaps/:id/progress', () => HttpResponse.json(buildProgress())),
    )
    // A different signed-in user (a reader/follower), not the owner.
    renderView(OTHER_USER)
    await screen.findByRole('progressbar', { name: /overall progress/i })

    // Any reader can fork a public roadmap; only the owner can edit its metadata.
    expect(screen.getByRole('button', { name: /^fork$/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /edit details/i })).not.toBeInTheDocument()
  })

  it('surfaces a retry message when a fork fails unexpectedly (500)', async () => {
    const user = userEvent.setup()
    server.use(
      http.get('*/roadmaps/:id', () => HttpResponse.json(buildDraft())),
      http.post(FORK_URL, () => new HttpResponse(null, { status: 500 })),
    )
    renderView()
    await screen.findByText('Grokking DSA')

    await user.click(screen.getByRole('button', { name: /^fork$/i }))

    expect(await screen.findByText(/couldn.t fork this roadmap/i)).toBeInTheDocument()
    // Did not navigate away: still on the source route.
    expect(screen.getByTestId('location')).toHaveTextContent(`/roadmaps/${ROADMAP_ID}`)
  })
})

describe('RoadmapView metadata edit', () => {
  const METADATA_URL = `${BASE}/roadmaps/${ROADMAP_ID}/metadata`

  it('lets the owner edit presentation metadata and reflects the new title', async () => {
    const user = userEvent.setup()
    let patched: unknown
    server.use(
      http.get('*/roadmaps/:id', () => HttpResponse.json(buildDraft())),
      http.patch(METADATA_URL, async ({ request }) => {
        patched = await request.json()
        const body = patched as { title: string; description: string; subject_tags: string[] }
        return HttpResponse.json(
          buildDraft({
            title: body.title,
            description: body.description,
            subject_tags: body.subject_tags,
          }),
        )
      }),
    )
    renderView()
    await screen.findByText('Grokking DSA')

    await user.click(screen.getByRole('button', { name: /edit details/i }))
    const titleInput = screen.getByLabelText('Title')
    await user.clear(titleInput)
    await user.type(titleInput, 'Renamed')
    const tagsInput = screen.getByLabelText('Subject tags')
    await user.clear(tagsInput)
    await user.type(tagsInput, 'cs, dsa')
    await user.click(screen.getByRole('button', { name: /save details/i }))

    // Only the three presentation fields are sent; parsed tags are trimmed.
    await waitFor(() =>
      expect(patched).toEqual({
        title: 'Renamed',
        description: 'A prerequisite-aware path.',
        subject_tags: ['cs', 'dsa'],
      }),
    )
    // The header reflects the returned roadmap and the editor closes.
    await waitFor(() =>
      expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Renamed'),
    )
    expect(screen.queryByRole('button', { name: /save details/i })).not.toBeInTheDocument()
  })

  it('edits metadata on a published roadmap (allowed post-publish)', async () => {
    const user = userEvent.setup()
    server.use(
      http.get('*/roadmaps/:id', () => HttpResponse.json(buildDraft({ status: 'published' }))),
      http.get('*/roadmaps/:id/progress', () => HttpResponse.json(buildProgress())),
      http.patch(METADATA_URL, () =>
        HttpResponse.json(buildDraft({ status: 'published', title: 'Renamed live' })),
      ),
    )
    renderView()
    await screen.findByRole('progressbar', { name: /overall progress/i })

    await user.click(screen.getByRole('button', { name: /edit details/i }))
    const titleInput = screen.getByLabelText('Title')
    await user.clear(titleInput)
    await user.type(titleInput, 'Renamed live')
    await user.click(screen.getByRole('button', { name: /save details/i }))

    await waitFor(() =>
      expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Renamed live'),
    )
    // Still the published tracking view (a metadata edit is not a lifecycle change).
    expect(
      screen.getByRole('progressbar', { name: /overall progress/i }),
    ).toBeInTheDocument()
  })

  it('keeps the editor open and shows a retry message when the edit fails (500)', async () => {
    const user = userEvent.setup()
    server.use(
      http.get('*/roadmaps/:id', () => HttpResponse.json(buildDraft())),
      http.patch(METADATA_URL, () => new HttpResponse(null, { status: 500 })),
    )
    renderView()
    await screen.findByText('Grokking DSA')

    await user.click(screen.getByRole('button', { name: /edit details/i }))
    const titleInput = screen.getByLabelText('Title')
    await user.clear(titleInput)
    await user.type(titleInput, 'Renamed')
    await user.click(screen.getByRole('button', { name: /save details/i }))

    expect(await screen.findByText(/couldn.t save your changes/i)).toBeInTheDocument()
    // The editor stays open so the entered values are not lost.
    expect(screen.getByRole('button', { name: /save details/i })).toBeInTheDocument()
  })

  it('closes the editor on Cancel without saving', async () => {
    const user = userEvent.setup()
    server.use(http.get('*/roadmaps/:id', () => HttpResponse.json(buildDraft())))
    renderView()
    await screen.findByText('Grokking DSA')

    await user.click(screen.getByRole('button', { name: /edit details/i }))
    expect(screen.getByRole('button', { name: /save details/i })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /cancel/i }))
    // The editor collapses; the toggle returns to "Edit details".
    expect(screen.queryByRole('button', { name: /save details/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /edit details/i })).toBeInTheDocument()
  })
})

describe('RoadmapView web-only lifecycle', () => {
  const VISIBILITY_URL = `${BASE}/roadmaps/${ROADMAP_ID}/visibility`
  const ARCHIVE_URL = `${BASE}/roadmaps/${ROADMAP_ID}:archive`
  const DELETE_URL = `${BASE}/roadmaps/${ROADMAP_ID}`
  const OTHER_USER = {
    id: 'user-2',
    username: 'grace',
    email: 'grace@example.com',
    created_at: '2026-07-15T00:00:00Z',
  }

  it('lets the owner toggle a draft public and flips the control', async () => {
    const user = userEvent.setup()
    let put: unknown
    server.use(
      http.get('*/roadmaps/:id', () => HttpResponse.json(buildDraft())),
      http.put(VISIBILITY_URL, async ({ request }) => {
        put = await request.json()
        const body = put as { visibility: 'public' | 'private' }
        return HttpResponse.json(buildDraft({ visibility: body.visibility }))
      }),
    )
    renderView()
    await screen.findByText('Grokking DSA')

    // Private draft: the toggle offers "Make public".
    await user.click(screen.getByRole('button', { name: /make public/i }))

    await waitFor(() => expect(put).toEqual({ visibility: 'public' }))
    // The returned roadmap replaces the loaded one, so the control flips.
    expect(await screen.findByRole('button', { name: /make private/i })).toBeInTheDocument()
  })

  it('does not offer Archive on a draft, but does offer Delete', async () => {
    server.use(http.get('*/roadmaps/:id', () => HttpResponse.json(buildDraft())))
    renderView()
    await screen.findByText('Grokking DSA')

    // Archive applies only to a published roadmap (linear lifecycle).
    expect(screen.queryByRole('button', { name: /^archive$/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^delete$/i })).toBeInTheDocument()
  })

  it('archives a published roadmap after confirmation and shows the archived badge', async () => {
    const user = userEvent.setup()
    server.use(
      http.get('*/roadmaps/:id', () => HttpResponse.json(buildDraft({ status: 'published' }))),
      http.get('*/roadmaps/:id/progress', () => HttpResponse.json(buildProgress())),
      http.post(ARCHIVE_URL, () => HttpResponse.json(buildDraft({ status: 'archived' }))),
    )
    renderView()
    await screen.findByRole('progressbar', { name: /overall progress/i })

    // Confirm-gated: the first click reveals a confirmation step.
    await user.click(screen.getByRole('button', { name: /^archive$/i }))
    await user.click(screen.getByRole('button', { name: /confirm archive/i }))

    // The archived badge appears and the Archive action is gone (already archived).
    expect(await screen.findByText('Archived')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^archive$/i })).not.toBeInTheDocument()
  })

  it('deletes a follower-free roadmap after confirmation and navigates away', async () => {
    const user = userEvent.setup()
    let deleted = false
    server.use(
      http.get('*/roadmaps/:id', () => HttpResponse.json(buildDraft())),
      http.delete(DELETE_URL, () => {
        deleted = true
        return new HttpResponse(null, { status: 204 })
      }),
    )
    renderView()
    await screen.findByText('Grokking DSA')

    await user.click(screen.getByRole('button', { name: /^delete$/i }))
    await user.click(screen.getByRole('button', { name: /confirm delete/i }))

    await waitFor(() => expect(deleted).toBe(true))
    // A successful delete leaves the now-removed roadmap's route.
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent(/^\/$/))
  })

  it('blocks delete when the roadmap has followers and steers to archive', async () => {
    const user = userEvent.setup()
    server.use(
      http.get('*/roadmaps/:id', () => HttpResponse.json(buildDraft({ status: 'published' }))),
      http.get('*/roadmaps/:id/progress', () => HttpResponse.json(buildProgress())),
      http.delete(DELETE_URL, () =>
        HttpResponse.json(
          {
            type: 'x',
            title: 'Conflict with the current state',
            status: 409,
            code: 'DELETE_HAS_FOLLOWERS',
            detail: 'Roadmap has 2 followers; archive it instead.',
          },
          { status: 409, headers: { 'content-type': 'application/problem+json' } },
        ),
      ),
    )
    renderView()
    await screen.findByRole('progressbar', { name: /overall progress/i })

    await user.click(screen.getByRole('button', { name: /^delete$/i }))
    await user.click(screen.getByRole('button', { name: /confirm delete/i }))

    // The 409 steers the owner to archive instead; the roadmap is not removed.
    expect(await screen.findByText(/archive it instead/i)).toBeInTheDocument()
    expect(screen.getByTestId('location')).toHaveTextContent(`/roadmaps/${ROADMAP_ID}`)
    // Archive remains available as the safe retirement path.
    expect(screen.getByRole('button', { name: /^archive$/i })).toBeInTheDocument()
  })

  it('cancels a destructive action without firing a request', async () => {
    const user = userEvent.setup()
    let deleteCalled = false
    server.use(
      http.get('*/roadmaps/:id', () => HttpResponse.json(buildDraft())),
      http.delete(DELETE_URL, () => {
        deleteCalled = true
        return new HttpResponse(null, { status: 204 })
      }),
    )
    renderView()
    await screen.findByText('Grokking DSA')

    await user.click(screen.getByRole('button', { name: /^delete$/i }))
    expect(screen.getByRole('button', { name: /confirm delete/i })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /cancel/i }))

    // The confirmation collapses and nothing was deleted.
    expect(screen.queryByRole('button', { name: /confirm delete/i })).not.toBeInTheDocument()
    expect(deleteCalled).toBe(false)
    expect(screen.getByRole('button', { name: /^delete$/i })).toBeInTheDocument()
  })

  it('hides all lifecycle actions from a non-owner', async () => {
    server.use(
      http.get('*/roadmaps/:id', () =>
        HttpResponse.json(buildDraft({ status: 'published', owner: 'user-1' })),
      ),
      http.get('*/roadmaps/:id/progress', () => HttpResponse.json(buildProgress())),
    )
    renderView(OTHER_USER)
    await screen.findByRole('progressbar', { name: /overall progress/i })

    // A reader who is not the owner sees Fork but none of the lifecycle actions.
    expect(screen.getByRole('button', { name: /^fork$/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^delete$/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^archive$/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /make public|make private/i })).not.toBeInTheDocument()
  })

  it('surfaces a retry message when a visibility toggle fails (500)', async () => {
    const user = userEvent.setup()
    server.use(
      http.get('*/roadmaps/:id', () => HttpResponse.json(buildDraft())),
      http.put(VISIBILITY_URL, () => new HttpResponse(null, { status: 500 })),
    )
    renderView()
    await screen.findByText('Grokking DSA')

    await user.click(screen.getByRole('button', { name: /make public/i }))
    expect(await screen.findByText(/couldn.t update visibility/i)).toBeInTheDocument()
    // Unchanged: still offers "Make public" (the toggle did not take effect).
    expect(screen.getByRole('button', { name: /make public/i })).toBeInTheDocument()
  })

  it('surfaces a retry message when archive fails (500)', async () => {
    const user = userEvent.setup()
    server.use(
      http.get('*/roadmaps/:id', () => HttpResponse.json(buildDraft({ status: 'published' }))),
      http.get('*/roadmaps/:id/progress', () => HttpResponse.json(buildProgress())),
      http.post(ARCHIVE_URL, () => new HttpResponse(null, { status: 500 })),
    )
    renderView()
    await screen.findByRole('progressbar', { name: /overall progress/i })

    await user.click(screen.getByRole('button', { name: /^archive$/i }))
    await user.click(screen.getByRole('button', { name: /confirm archive/i }))
    expect(await screen.findByText(/couldn.t archive this roadmap/i)).toBeInTheDocument()
    // Not archived: the Archive action remains available to retry.
    expect(screen.getByRole('button', { name: /^archive$/i })).toBeInTheDocument()
  })
})

describe('RoadmapView list view (tags, filter chips, next highlight)', () => {
  const PROGRESS_URL = `${BASE}/roadmaps/${ROADMAP_ID}/progress`
  const NEXT_URL = `${BASE}/roadmaps/${ROADMAP_ID}/next`

  /**
   * A published roadmap with two subsections carrying distinct track tags, so
   * the filter chips and per-subsection filtering are exercisable end-to-end.
   */
  function filterableRoadmap(): Roadmap {
    return buildDraft({
      status: 'published',
      section_order: ['sec_foundations'],
      suggested_path: ['sub_arrays', 'sub_hashing'],
      sections: {
        sec_foundations: {
          id: 'sec_foundations',
          title: 'Foundations',
          subsection_order: ['sub_arrays', 'sub_hashing'],
          subsections: {
            sub_arrays: {
              id: 'sub_arrays',
              title: 'Arrays & two pointers',
              tags: ['arrays'],
              prereq_ids: [],
              resource_order: [],
              resources: {},
              item_order: ['chk_read'],
              checklist_items: { chk_read: { id: 'chk_read', text: 'Read the walkthrough' } },
            },
            sub_hashing: {
              id: 'sub_hashing',
              title: 'Hashing',
              tags: ['hashing'],
              prereq_ids: [],
              resource_order: [],
              resources: {},
              item_order: ['chk_hash'],
              checklist_items: { chk_hash: { id: 'chk_hash', text: 'Implement a counter' } },
            },
          },
        },
      },
    })
  }

  it('renders one filter chip per distinct track tag', async () => {
    server.use(
      http.get('*/roadmaps/:id', () => HttpResponse.json(filterableRoadmap())),
      http.get(PROGRESS_URL, () => HttpResponse.json(buildProgress())),
    )
    renderView()

    const group = await screen.findByRole('group', { name: /filter by tag/i })
    // One chip per track tag, in first-appearance order; subject tags excluded.
    expect(within(group).getAllByRole('button').map((chip) => chip.textContent)).toEqual([
      'arrays',
      'hashing',
    ])
  })

  it('filters subsections to the selected tag and clears on re-select', async () => {
    const user = userEvent.setup()
    server.use(
      http.get('*/roadmaps/:id', () => HttpResponse.json(filterableRoadmap())),
      http.get(PROGRESS_URL, () => HttpResponse.json(buildProgress())),
    )
    renderView()

    const group = await screen.findByRole('group', { name: /filter by tag/i })
    const arraysChip = within(group).getByRole('button', { name: 'arrays' })
    // Both subsections visible before any filter.
    expect(screen.getByRole('heading', { level: 3, name: 'Arrays & two pointers' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 3, name: 'Hashing' })).toBeInTheDocument()

    await user.click(arraysChip)

    // Active chip is styled/announced active; only the matching subsection shows.
    expect(arraysChip).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('heading', { level: 3, name: 'Arrays & two pointers' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { level: 3, name: 'Hashing' })).not.toBeInTheDocument()

    // Re-selecting the active chip clears the filter and restores all subsections.
    await user.click(arraysChip)
    expect(arraysChip).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByRole('heading', { level: 3, name: 'Hashing' })).toBeInTheDocument()
  })

  it('renders no filter chips when the roadmap has no track tags', async () => {
    const untagged = buildDraft({
      status: 'published',
      section_order: ['sec_only'],
      suggested_path: [],
      sections: {
        sec_only: {
          id: 'sec_only',
          title: 'Only section',
          subsection_order: ['sub_bare'],
          subsections: {
            sub_bare: {
              id: 'sub_bare',
              title: 'Bare node',
              tags: [],
              prereq_ids: [],
              resource_order: [],
              resources: {},
              item_order: ['chk_x'],
              checklist_items: { chk_x: { id: 'chk_x', text: 'Only item' } },
            },
          },
        },
      },
    })
    server.use(
      http.get('*/roadmaps/:id', () => HttpResponse.json(untagged)),
      http.get(PROGRESS_URL, () => HttpResponse.json(buildProgress())),
    )
    renderView()

    await screen.findByRole('heading', { level: 3, name: 'Bare node' })
    expect(screen.queryByRole('group', { name: /filter by tag/i })).not.toBeInTheDocument()
  })

  it('hash-colors track-tag pills via the shared util and leaves subject tags neutral', async () => {
    server.use(
      http.get('*/roadmaps/:id', () => HttpResponse.json(filterableRoadmap())),
      http.get(PROGRESS_URL, () => HttpResponse.json(buildProgress())),
    )
    renderView()

    // The track-tag pill inside the node card carries the stable hash hue.
    const card = (
      await screen.findByRole('heading', { level: 3, name: 'Arrays & two pointers' })
    ).closest('article') as HTMLElement
    const pill = within(card).getByText('arrays')
    expect(pill.style.getPropertyValue('--tag-hue')).toBe(colorForTag('arrays'))

    // The roadmap-level subject tag is a neutral chip: never hash-colored.
    const subjectTag = screen.getByText('computer-science')
    expect(subjectTag.style.getPropertyValue('--tag-hue')).toBe('')
  })

  it('highlights the current "next" subsection (from GET /next) with aria-current', async () => {
    server.use(
      http.get('*/roadmaps/:id', () => HttpResponse.json(filterableRoadmap())),
      http.get(PROGRESS_URL, () => HttpResponse.json(buildProgress())),
      http.get(NEXT_URL, () =>
        HttpResponse.json({
          items: [
            {
              subsection_id: 'sub_arrays',
              item_id: 'chk_read',
              text: 'Read the walkthrough',
              why_now:
                'Next unchecked subsection in the suggested path; it has no prerequisites.',
            },
          ],
          remaining_in_path: 2,
          complete: false,
        }),
      ),
    )
    renderView()

    await screen.findByRole('progressbar', { name: /overall progress/i })
    // The "next" node is highlighted; the highlight lands only on that card.
    await waitFor(() =>
      expect(
        screen.getByRole('heading', { level: 3, name: 'Arrays & two pointers' }).closest('article'),
      ).toHaveAttribute('aria-current', 'step'),
    )
    expect(
      screen.getByRole('heading', { level: 3, name: 'Hashing' }).closest('article'),
    ).not.toHaveAttribute('aria-current')
  })
})

describe('RoadmapView states (loading/empty/error, 409/422, tabs, anchor)', () => {
  const PROGRESS_URL = `${BASE}/roadmaps/${ROADMAP_ID}/progress`
  const NEXT_URL = `${BASE}/roadmaps/${ROADMAP_ID}/next`
  const PUBLISH_URL = `${BASE}/roadmaps/${ROADMAP_ID}:publish`

  /** A 409 problem+json body with the given machine code. */
  function conflict(code: string, detail: string) {
    return HttpResponse.json(
      { type: 'x', title: 'Conflict with the current state', status: 409, code, detail },
      { status: 409, headers: { 'content-type': 'application/problem+json' } },
    )
  }

  it('surfaces an ochre re-read prompt (color AND text) when a progress write is stale (409)', async () => {
    const user = userEvent.setup()
    server.use(
      http.get('*/roadmaps/:id', () => HttpResponse.json(buildDraft({ status: 'published' }))),
      http.get(PROGRESS_URL, () => HttpResponse.json(buildProgress())),
      http.post(PROGRESS_URL, () =>
        conflict('STALE_REVISION', 'This roadmap changed; re-read and retry.'),
      ),
    )
    renderView()

    const checkbox = await screen.findByRole('checkbox', { name: 'Read the walkthrough' })
    await user.click(checkbox)

    // The stale write becomes the first-class ochre re-read prompt, not a toast.
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/reload to continue/i)
    // Meaning is reinforced by ochre, but never carried by color alone (text + icon).
    expect(alert.className).toMatch(/warning/)
    // The optimistic check was rolled back to match the server.
    await waitFor(() => expect(checkbox).not.toBeChecked())

    // Reloading clears the prompt and refetches fresh state.
    await user.click(within(alert).getByRole('button', { name: 'Reload' }))
    await waitFor(() => expect(screen.queryByText(/reload to continue/i)).not.toBeInTheDocument())
  })

  it('surfaces a quiet inline notice (not silent) and reverts when a progress write fails (500)', async () => {
    const user = userEvent.setup()
    server.use(
      http.get('*/roadmaps/:id', () => HttpResponse.json(buildDraft({ status: 'published' }))),
      http.get(PROGRESS_URL, () => HttpResponse.json(buildProgress())),
      http.post(PROGRESS_URL, () => new HttpResponse(null, { status: 500 })),
    )
    renderView()

    const checkbox = await screen.findByRole('checkbox', { name: 'Read the walkthrough' })
    await user.click(checkbox)

    // A failed persist is announced (never a silent revert) ...
    expect(await screen.findByRole('status')).toHaveTextContent(/couldn.t save that change/i)
    // ... and the optimistic check is rolled back.
    await waitFor(() => expect(checkbox).not.toBeChecked())
  })

  it('steers a 409 immutable publish to fork-to-change', async () => {
    const user = userEvent.setup()
    server.use(
      http.get('*/roadmaps/:id', () => HttpResponse.json(buildDraft())),
      http.post(PUBLISH_URL, () =>
        conflict('IMMUTABLE', 'Already published; fork to change.'),
      ),
    )
    renderView()
    await screen.findByText('Grokking DSA')

    await user.click(screen.getByRole('button', { name: /^publish$/i }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/fork it to make changes/i)
    expect(within(alert).getByRole('button', { name: 'Fork to change' })).toBeInTheDocument()
  })

  it('renders a calm completion state when the suggested path is complete', async () => {
    server.use(
      http.get('*/roadmaps/:id', () => HttpResponse.json(buildDraft({ status: 'published' }))),
      http.get(PROGRESS_URL, () => HttpResponse.json(buildProgress(['chk_read', 'chk_hash']))),
      http.get(NEXT_URL, () => HttpResponse.json({ items: [], remaining_in_path: 0, complete: true })),
    )
    renderView()

    expect(await screen.findByText(/all caught up/i)).toBeInTheDocument()
  })

  it('offers a List->Tree entry point in the published list header', async () => {
    server.use(
      http.get('*/roadmaps/:id', () => HttpResponse.json(buildDraft({ status: 'published' }))),
      http.get(PROGRESS_URL, () => HttpResponse.json(buildProgress())),
    )
    renderView()
    await screen.findByRole('progressbar', { name: /overall progress/i })

    const tabs = screen.getByRole('navigation', { name: 'Roadmap views' })
    expect(within(tabs).getByRole('link', { name: 'Tree' })).toHaveAttribute(
      'href',
      `/roadmaps/${ROADMAP_ID}/tree`,
    )
  })

  it('renders per-subsection anchor targets and scrolls to the URL hash', async () => {
    const scrollSpy = vi.spyOn(Element.prototype, 'scrollIntoView').mockImplementation(() => {})
    server.use(
      http.get('*/roadmaps/:id', () => HttpResponse.json(buildDraft({ status: 'published' }))),
      http.get(PROGRESS_URL, () => HttpResponse.json(buildProgress())),
    )
    renderViewAtHash('#sub_arrays')

    await screen.findByRole('heading', { level: 3, name: 'Arrays & two pointers' })
    // The list-view anchor target the tree links to is present ...
    const anchor = document.getElementById('sub_arrays')
    expect(anchor).not.toBeNull()
    // ... and the hash scrolls that node into view.
    await waitFor(() => expect(scrollSpy).toHaveBeenCalled())
    scrollSpy.mockRestore()
  })
})

describe('RoadmapView sub-state reset on roadmapId change (R2 invariant)', () => {
  const ROADMAP_B = 'algorithms-ii-9x2b'
  const PUBLISH_URL = `${BASE}/roadmaps/${ROADMAP_ID}:publish`

  /** A 422 hard-block carrying one structural violation, to drive the publish
   *  sub-state into `blocked` (the state that must not leak across roadmaps). */
  function blockedPublish() {
    return HttpResponse.json(
      {
        type: 'x',
        title: 'Draft cannot be published',
        status: 422,
        code: 'VALIDATION',
        violations: [
          {
            rule: 'V7_RESOURCE_REQUIRED',
            ids: ['sub_hashing'],
            message: 'subsection sub_hashing has no resources',
          },
        ],
      },
      { status: 422, headers: { 'content-type': 'application/problem+json' } },
    )
  }

  it('clears a blocked publish sub-state when the route changes on the same instance', async () => {
    const user = userEvent.setup()
    server.use(
      http.post('*/auth/refresh', () => HttpResponse.json(AUTH_USER)),
      // Both roadmap A and roadmap B resolve to an owned draft (echo the id), so
      // the only thing that could differ between them is a leaked sub-state.
      http.get('*/roadmaps/:id', ({ params }) =>
        HttpResponse.json(buildDraft({ id: String(params.id) })),
      ),
      http.post(PUBLISH_URL, () => blockedPublish()),
    )
    renderWithProviders(
      <>
        <Routes>
          <Route path="/roadmaps/:roadmapId" element={<RoadmapView />} />
        </Routes>
        <NavTo to={`/roadmaps/${ROADMAP_B}`} label="Go to roadmap B" />
      </>,
      { initialEntries: [`/roadmaps/${ROADMAP_ID}`], baseUrl: BASE, useRealAuth: true },
    )

    await screen.findByText('Grokking DSA')
    await user.click(screen.getByRole('button', { name: /^publish$/i }))
    // Roadmap A's publish is hard-blocked: the violation is shown inline.
    expect(
      await screen.findByText('subsection sub_hashing has no resources'),
    ).toBeInTheDocument()

    // Navigate to roadmap B WITHOUT unmounting RoadmapView: React Router keeps the
    // same instance across a `:roadmapId` change, so the plain-useState publish
    // sub-state would leak onto B unless it is reset (the R2 invariant).
    await user.click(screen.getByRole('button', { name: /go to roadmap b/i }))

    // Once roadmap B is loaded (its Publish action is back), the blocked violation
    // from roadmap A is gone: the sub-state reset fired on the route change.
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /^publish$/i })).toBeInTheDocument()
      expect(
        screen.queryByText('subsection sub_hashing has no resources'),
      ).not.toBeInTheDocument()
    })
    expect(screen.getByText(/draft · preview/i)).toBeInTheDocument()
  })
})

