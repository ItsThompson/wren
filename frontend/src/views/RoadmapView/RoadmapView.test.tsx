import { render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router'

import type { Roadmap } from './types'
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
