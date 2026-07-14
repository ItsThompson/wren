import type {
  MockDashboard,
  MockNext,
  MockOverview,
  MockProfile,
  MockProgressSnapshot,
  MockRoadmap,
} from './types'

/**
 * Coherent dev fixtures for the MSW harness. One published roadmap plus the
 * dashboard/profile/progress projections built from it, so the SPA can run with
 * zero backend (`npm run dev:mock`). Ids use the section-06 slug form
 * (`{title-slug}-{short-random}`).
 */

export const OWNER_HANDLE = 'ada'

export const mockRoadmap: MockRoadmap = {
  id: 'grokking-dsa-7f3k',
  title: 'Grokking Data Structures & Algorithms',
  description:
    'A prerequisite-aware path from arrays to graph algorithms, sequenced so each node sits just past what the last one taught.',
  subject_tags: ['computer-science', 'interview-prep'],
  status: 'published',
  visibility: 'public',
  owner_handle: OWNER_HANDLE,
  revision: 12,
  suggested_path: ['sub_arrays', 'sub_hashing', 'sub_recursion', 'sub_graphs'],
  sections: [
    {
      id: 'sec_foundations',
      title: 'Foundations',
      subsection_order: ['sub_arrays', 'sub_hashing'],
      subsections: [
        {
          id: 'sub_arrays',
          title: 'Arrays & two pointers',
          track_tags: ['arrays', 'two-pointers'],
          effort: '3h',
          prereq_ids: [],
          resources: [
            {
              type: 'article',
              title: 'Two-pointer technique',
              url: 'https://example.com/two-pointers',
            },
            {
              type: 'exercise',
              title: 'Pair-sum drills',
              url: 'https://example.com/pair-sum',
            },
          ],
          checklist_items: [
            { id: 'item_arrays_read', text: 'Read the two-pointer walkthrough' },
            { id: 'item_arrays_drill', text: 'Solve three pair-sum problems' },
          ],
        },
        {
          id: 'sub_hashing',
          title: 'Hashing & frequency maps',
          track_tags: ['hashing'],
          effort: '2h',
          prereq_ids: ['sub_arrays'],
          resources: [
            {
              type: 'video',
              title: 'Hash maps from scratch',
              url: 'https://example.com/hash-maps',
            },
          ],
          checklist_items: [
            { id: 'item_hashing_read', text: 'Watch the hash-map explainer' },
            { id: 'item_hashing_drill', text: 'Implement a frequency counter' },
          ],
        },
      ],
    },
    {
      id: 'sec_recursion-graphs',
      title: 'Recursion & graphs',
      subsection_order: ['sub_recursion', 'sub_graphs'],
      subsections: [
        {
          id: 'sub_recursion',
          title: 'Recursion & backtracking',
          track_tags: ['recursion', 'backtracking'],
          effort: '4h',
          prereq_ids: ['sub_hashing'],
          resources: [
            {
              type: 'course',
              title: 'Thinking recursively',
              url: 'https://example.com/recursion',
            },
          ],
          checklist_items: [
            { id: 'item_recursion_read', text: 'Work through the call-stack model' },
            { id: 'item_recursion_drill', text: 'Solve the subsets problem' },
          ],
        },
        {
          id: 'sub_graphs',
          title: 'Graph traversal',
          track_tags: ['graphs', 'bfs-dfs'],
          effort: '5h',
          prereq_ids: ['sub_recursion'],
          resources: [
            {
              type: 'article',
              title: 'BFS vs DFS',
              url: 'https://example.com/bfs-dfs',
            },
          ],
          checklist_items: [
            { id: 'item_graphs_read', text: 'Read the traversal comparison' },
            { id: 'item_graphs_drill', text: 'Implement BFS and DFS' },
          ],
        },
      ],
    },
  ],
}

/** Arrays section fully done; the learner is partway into hashing. */
export const mockProgress: MockProgressSnapshot = {
  roadmap_id: mockRoadmap.id,
  checked_item_ids: ['item_arrays_read', 'item_arrays_drill', 'item_hashing_read'],
  overall_completed: 3,
  overall_total: 8,
  sections: [
    { section_id: 'sec_foundations', completed: 3, total: 4 },
    { section_id: 'sec_recursion-graphs', completed: 0, total: 4 },
  ],
}

export const mockOverview: MockOverview = {
  id: mockRoadmap.id,
  title: mockRoadmap.title,
  subject_tags: mockRoadmap.subject_tags,
  overall_completed: mockProgress.overall_completed,
  overall_total: mockProgress.overall_total,
  sections: mockRoadmap.sections.map((section) => {
    const progress = mockProgress.sections.find(
      (entry) => entry.section_id === section.id,
    )
    return {
      id: section.id,
      title: section.title,
      progress: progress ?? {
        section_id: section.id,
        completed: 0,
        total: section.subsections.length,
      },
    }
  }),
}

export const mockNext: MockNext = {
  roadmap_id: mockRoadmap.id,
  items: [
    {
      subsection_id: 'sub_hashing',
      item_id: 'item_hashing_drill',
      title: 'Implement a frequency counter',
      why_now: 'Its only prerequisite (arrays & two pointers) is complete.',
    },
  ],
  remaining_in_path: 5,
  complete: false,
}

export const mockDashboard: MockDashboard = {
  authored: [
    {
      id: mockRoadmap.id,
      title: mockRoadmap.title,
      status: mockRoadmap.status,
      visibility: mockRoadmap.visibility,
      subject_tags: mockRoadmap.subject_tags,
    },
    {
      id: 'systems-design-primer-9x2b',
      title: 'Systems Design Primer',
      status: 'draft',
      visibility: 'private',
      subject_tags: ['systems-design'],
    },
  ],
  followed: [
    {
      id: 'grokking-dsa-7f3k',
      title: mockRoadmap.title,
      status: 'published',
      visibility: 'public',
      subject_tags: mockRoadmap.subject_tags,
    },
  ],
}

export const mockProfile: MockProfile = {
  handle: OWNER_HANDLE,
  display_name: 'Ada Lovelace',
  roadmaps: [
    {
      id: mockRoadmap.id,
      title: mockRoadmap.title,
      status: mockRoadmap.status,
      visibility: mockRoadmap.visibility,
      subject_tags: mockRoadmap.subject_tags,
    },
  ],
}
