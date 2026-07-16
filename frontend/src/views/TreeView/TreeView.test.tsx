import type { ComponentType } from 'react'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { Route, Routes, useLocation } from 'react-router'
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/renderWithProviders'

import type { ProgressSnapshot, Roadmap, TreeNodeData } from './types'
import { TreeView } from './TreeView'

/**
 * React Flow performs no real layout under jsdom, so we mock it: we
 * test the state-mapping + navigation + node props, not pixel layout. The mock
 * renders each node through its registered `nodeTypes` component and exposes the
 * edges + laid-out y so the built graph is assertable end-to-end.
 */
vi.mock('@xyflow/react', () => {
  const Position = { Top: 'top', Bottom: 'bottom', Left: 'left', Right: 'right' }
  interface MockNode {
    id: string
    type: string
    position: { x: number; y: number }
    data: TreeNodeData
  }
  interface MockFlowProps {
    nodes: MockNode[]
    edges: { id: string; source: string; target: string }[]
    nodeTypes: Record<string, ComponentType<{ id: string; data: TreeNodeData }>>
  }
  return {
    Position,
    Background: () => null,
    Controls: () => null,
    Handle: () => null,
    ReactFlow: ({ nodes, edges, nodeTypes }: MockFlowProps) => (
      <div data-testid="react-flow">
        <div data-testid="edge-count">{edges.length}</div>
        {nodes.map((node) => {
          const NodeComponent = nodeTypes[node.type]
          return (
            <div key={node.id} data-testid="rf-node" data-node-id={node.id} data-node-y={node.position.y}>
              <NodeComponent id={node.id} data={node.data} />
            </div>
          )
        })}
      </div>
    ),
  }
})

const BASE = 'https://api.test'
const ROADMAP_ID = 'grokking-dsa-7f3k'

/** A published roadmap with a prerequisite chain: Arrays -> Hashing -> Trees. */
function buildRoadmap(overrides: Partial<Roadmap> = {}): Roadmap {
  return {
    id: ROADMAP_ID,
    owner: 'user-1',
    title: 'Grokking DSA',
    visibility: 'public',
    status: 'published',
    revision: 3,
    section_order: ['sec_1'],
    sections: {
      sec_1: {
        id: 'sec_1',
        title: 'Foundations',
        subsection_order: ['a', 'b', 'c'],
        subsections: {
          a: { id: 'a', title: 'Arrays', prereq_ids: [], item_order: ['a1'] },
          b: { id: 'b', title: 'Hashing', prereq_ids: ['a'], item_order: ['b1'] },
          c: { id: 'c', title: 'Binary trees', prereq_ids: ['b'], item_order: ['c1'] },
        },
      },
    },
    created_at: '2026-07-15T00:00:00Z',
    updated_at: '2026-07-15T00:00:00Z',
    ...overrides,
  }
}

function buildProgress(checkedIds: string[] = []): ProgressSnapshot {
  return {
    roadmap_id: ROADMAP_ID,
    total_items: 3,
    checked_items: checkedIds.length,
    percent: 0,
    checked_ids: checkedIds,
  }
}

const server = setupServer(
  // useRealAuth mounts the real AuthProvider, which resumes via POST /auth/refresh
  // on mount; resolve it to anonymous (the tree read is unconditional either way).
  http.post('*/auth/refresh', () => new HttpResponse(null, { status: 401 })),
  http.get('*/roadmaps/:id/progress', () => HttpResponse.json(buildProgress([]))),
  http.get('*/roadmaps/:id', () => HttpResponse.json(buildRoadmap())),
)

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

/** Renders the current location so click-navigation is assertable. */
function LocationProbe() {
  const location = useLocation()
  return (
    <div data-testid="location">
      {location.pathname}
      {location.hash}
    </div>
  )
}

function renderTree() {
  return renderWithProviders(
    <>
      <Routes>
        <Route path="/roadmaps/:roadmapId/tree" element={<TreeView />} />
        <Route path="/roadmaps/:roadmapId" element={<div>list view stub</div>} />
      </Routes>
      <LocationProbe />
    </>,
    { initialEntries: [`/roadmaps/${ROADMAP_ID}/tree`], baseUrl: BASE, useRealAuth: true },
  )
}

function nodeLink(title: string): HTMLElement {
  return screen.getByRole('link', { name: new RegExp(`^${title} \\(`) })
}

describe('TreeView', () => {
  it('renders subsections as nodes and prereq_ids as edges in a layered layout', async () => {
    renderTree()

    // One node per subsection.
    expect(await screen.findByRole('link', { name: /^Arrays \(/ })).toBeInTheDocument()
    expect(screen.getAllByTestId('rf-node')).toHaveLength(3)
    // Two prerequisite edges: Arrays -> Hashing -> Binary trees.
    expect(screen.getByTestId('edge-count')).toHaveTextContent('2')

    // Layered top-down: the prerequisite (Arrays) sits above its dependent (Hashing).
    const byId = (id: string) =>
      Number(screen.getAllByTestId('rf-node').find((el) => el.dataset.nodeId === id)?.dataset.nodeY)
    expect(byId('a')).toBeLessThan(byId('b'))
  })

  it('derives soft-state from progress + prereqs (color + icon via data-state)', async () => {
    renderTree()
    await screen.findByRole('link', { name: /^Arrays \(/ })

    // No progress: root available, dependents locked.
    expect(nodeLink('Arrays')).toHaveAttribute('data-state', 'available')
    expect(nodeLink('Hashing')).toHaveAttribute('data-state', 'locked')
    expect(nodeLink('Binary trees')).toHaveAttribute('data-state', 'locked')
  })

  it('marks a node done and unlocks its dependent from the progress record', async () => {
    server.use(http.get('*/roadmaps/:id/progress', () => HttpResponse.json(buildProgress(['a1']))))
    renderTree()
    await screen.findByRole('link', { name: /^Arrays \(/ })

    await waitFor(() => expect(nodeLink('Arrays')).toHaveAttribute('data-state', 'done'))
    expect(nodeLink('Hashing')).toHaveAttribute('data-state', 'available')
    expect(nodeLink('Binary trees')).toHaveAttribute('data-state', 'locked')
  })

  it('keeps locked nodes clickable and navigates to the subsection in the list view', async () => {
    const user = userEvent.setup()
    renderTree()
    const hashing = await screen.findByRole('link', { name: /^Hashing \(locked\)/ })
    expect(hashing).toHaveAttribute('href', `/roadmaps/${ROADMAP_ID}#b`)

    await user.click(hashing)

    // Navigated to the list view route with the subsection anchor.
    expect(screen.getByText('list view stub')).toBeInTheDocument()
    expect(screen.getByTestId('location')).toHaveTextContent(`/roadmaps/${ROADMAP_ID}#b`)
  })

  it('renders no per-node progress bars', async () => {
    renderTree()
    await screen.findByRole('link', { name: /^Arrays \(/ })
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
  })

  it('still renders the tree when the progress record is unavailable', async () => {
    server.use(http.get('*/roadmaps/:id/progress', () => HttpResponse.error()))
    renderTree()
    await screen.findByRole('link', { name: /^Arrays \(/ })

    // No progress reachable: every node falls back to its base state.
    expect(nodeLink('Arrays')).toHaveAttribute('data-state', 'available')
    expect(nodeLink('Hashing')).toHaveAttribute('data-state', 'locked')
  })

  it('shows a not-found message when the roadmap is unreachable (404)', async () => {
    server.use(
      http.get('*/roadmaps/:id', () =>
        HttpResponse.json(
          { type: 'x', title: 'Resource not found', status: 404, code: 'NOT_FOUND' },
          { status: 404, headers: { 'content-type': 'application/problem+json' } },
        ),
      ),
    )
    renderTree()
    expect(await screen.findByText('Roadmap not found')).toBeInTheDocument()
  })

  it('shows a not-found message on a network failure', async () => {
    server.use(http.get('*/roadmaps/:id', () => HttpResponse.error()))
    renderTree()
    expect(await screen.findByText('Roadmap not found')).toBeInTheDocument()
  })

  it('offers a Tree->List entry point in the header (List links to the list view)', async () => {
    renderTree()
    await screen.findByRole('link', { name: /^Arrays \(/ })

    const tabs = screen.getByRole('navigation', { name: 'Roadmap views' })
    expect(within(tabs).getByRole('link', { name: 'List' })).toHaveAttribute(
      'href',
      `/roadmaps/${ROADMAP_ID}`,
    )
    // Tree is the active view, announced (not a link) so it never self-links.
    expect(within(tabs).queryByRole('link', { name: 'Tree' })).not.toBeInTheDocument()
  })

  it('shows an empty-state message when the roadmap has no subsections', async () => {
    server.use(
      http.get('*/roadmaps/:id', () =>
        HttpResponse.json(buildRoadmap({ section_order: [], sections: {} })),
      ),
    )
    renderTree()

    expect(await screen.findByText('No nodes yet')).toBeInTheDocument()
    // The header still renders with a link back to the list view.
    const header = screen.getByRole('navigation', { name: 'Roadmap views' })
    expect(within(header).getByRole('link', { name: 'List' })).toHaveAttribute(
      'href',
      `/roadmaps/${ROADMAP_ID}`,
    )
  })
})
