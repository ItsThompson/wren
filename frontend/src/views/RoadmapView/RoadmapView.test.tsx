import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router'

import type { ProgressSnapshot, ProgressUpdateResult, Roadmap } from './types'
import { RoadmapView } from './RoadmapView'

const BASE = 'https://api.test'
const ROADMAP_ID = 'grokking-dsa-7f3k'

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

const server = setupServer()

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
  return { progress: buildProgress(checkedIds), next: { items: [], complete: false } }
}

function renderView() {
  return render(
    <MemoryRouter initialEntries={[`/roadmaps/${ROADMAP_ID}`]}>
      <Routes>
        <Route path="/roadmaps/:roadmapId" element={<RoadmapView baseUrl={BASE} />} />
      </Routes>
    </MemoryRouter>,
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

    fireEvent.click(screen.getByRole('button', { name: /^publish$/i }))

    // The offending rule + message are surfaced inline for the author to fix.
    expect(await screen.findByText('subsection sub_hashing has no resources')).toBeInTheDocument()
    expect(screen.getByText('V7_RESOURCE_REQUIRED')).toBeInTheDocument()
    // Hard-block: the roadmap stays a draft.
    expect(screen.getByText(/draft · preview/i)).toBeInTheDocument()
  })

  it('routes to the tracking list view after a successful publish (200)', async () => {
    server.use(
      http.get('*/roadmaps/:id', () => HttpResponse.json(buildDraft())),
      http.post(PUBLISH_URL, () => HttpResponse.json(buildDraft({ status: 'published' }))),
      http.get('*/roadmaps/:id/progress', () => HttpResponse.json(buildProgress())),
    )
    renderView()
    await screen.findByText('Grokking DSA')

    fireEvent.click(screen.getByRole('button', { name: /^publish$/i }))

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
    server.use(
      http.get('*/roadmaps/:id', () => HttpResponse.json(buildDraft())),
      http.post(PUBLISH_URL, () => new HttpResponse(null, { status: 500 })),
    )
    renderView()
    await screen.findByText('Grokking DSA')

    fireEvent.click(screen.getByRole('button', { name: /^publish$/i }))

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

    fireEvent.click(screen.getByRole('checkbox', { name: 'Read the walkthrough' }))

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
    fireEvent.click(checkbox)

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

