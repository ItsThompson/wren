import type {
  MockAuthenticatedUser,
  MockDashboard,
  MockNext,
  MockOverview,
  MockProfile,
  MockProgressSnapshot,
  MockRoadmap,
} from './types'

/**
 * Coherent dev fixtures for the MSW harness, in the OpenAPI-generated schema
 * shape. One published roadmap plus the dashboard/profile/progress
 * projections built from it, so the SPA renders populated views with zero backend
 * (`npm run dev:mock`). The roadmap uses the section-04 ID-keyed maps
 * (`sections` / `subsections` / `resources` / `checklist_items`) with explicit
 * `*_order` arrays, and slug ids in the section-06 form (`{title-slug}-{short}`).
 */

export const OWNER_ID = 'usr_ada'
export const OWNER_HANDLE = 'ada'

export const mockRoadmap: MockRoadmap = {
  id: 'grokking-dsa-7f3k',
  owner: OWNER_ID,
  title: 'Grokking Data Structures & Algorithms',
  description:
    'A prerequisite-aware path from arrays to graph algorithms, sequenced so each node sits just past what the last one taught.',
  subject_tags: ['computer-science', 'interview-prep'],
  visibility: 'public',
  status: 'published',
  revision: 12,
  section_order: ['sec_foundations', 'sec_recursion-graphs'],
  suggested_path: ['sub_arrays', 'sub_hashing', 'sub_recursion', 'sub_graphs'],
  sections: {
    sec_foundations: {
      id: 'sec_foundations',
      title: 'Foundations',
      subsection_order: ['sub_arrays', 'sub_hashing'],
      subsections: {
        sub_arrays: {
          id: 'sub_arrays',
          title: 'Arrays & two pointers',
          description: 'Scan and shrink windows in place before reaching for extra space.',
          tags: ['arrays', 'two-pointers'],
          effort_estimate: '3h',
          prereq_ids: [],
          resource_order: ['res_two_pointers', 'res_pair_sum'],
          resources: {
            res_two_pointers: {
              id: 'res_two_pointers',
              title: 'Two-pointer technique',
              url: 'https://example.com/two-pointers',
              type: 'article',
            },
            res_pair_sum: {
              id: 'res_pair_sum',
              title: 'Pair-sum drills',
              url: 'https://example.com/pair-sum',
              type: 'other',
            },
          },
          item_order: ['item_arrays_read', 'item_arrays_drill'],
          checklist_items: {
            item_arrays_read: { id: 'item_arrays_read', text: 'Read the two-pointer walkthrough' },
            item_arrays_drill: { id: 'item_arrays_drill', text: 'Solve three pair-sum problems' },
          },
        },
        sub_hashing: {
          id: 'sub_hashing',
          title: 'Hashing & frequency maps',
          description: 'Trade space for O(1) lookups and count things in one pass.',
          tags: ['hashing'],
          effort_estimate: '2h',
          prereq_ids: ['sub_arrays'],
          resource_order: ['res_hash_maps'],
          resources: {
            res_hash_maps: {
              id: 'res_hash_maps',
              title: 'Hash maps from scratch',
              url: 'https://example.com/hash-maps',
              type: 'video',
            },
          },
          item_order: ['item_hashing_read', 'item_hashing_drill'],
          checklist_items: {
            item_hashing_read: { id: 'item_hashing_read', text: 'Watch the hash-map explainer' },
            item_hashing_drill: { id: 'item_hashing_drill', text: 'Implement a frequency counter' },
          },
        },
      },
    },
    'sec_recursion-graphs': {
      id: 'sec_recursion-graphs',
      title: 'Recursion & graphs',
      subsection_order: ['sub_recursion', 'sub_graphs'],
      subsections: {
        sub_recursion: {
          id: 'sub_recursion',
          title: 'Recursion & backtracking',
          description: 'Trust the call stack, then prune the search space.',
          tags: ['recursion', 'backtracking'],
          effort_estimate: '4h',
          prereq_ids: ['sub_hashing'],
          resource_order: ['res_recursion'],
          resources: {
            res_recursion: {
              id: 'res_recursion',
              title: 'Thinking recursively',
              url: 'https://example.com/recursion',
              type: 'course',
            },
          },
          item_order: ['item_recursion_read', 'item_recursion_drill'],
          checklist_items: {
            item_recursion_read: { id: 'item_recursion_read', text: 'Work through the call-stack model' },
            item_recursion_drill: { id: 'item_recursion_drill', text: 'Solve the subsets problem' },
          },
        },
        sub_graphs: {
          id: 'sub_graphs',
          title: 'Graph traversal',
          description: 'BFS for shortest hops, DFS for reachability and cycles.',
          tags: ['graphs', 'bfs-dfs'],
          effort_estimate: '5h',
          prereq_ids: ['sub_recursion'],
          resource_order: ['res_bfs_dfs'],
          resources: {
            res_bfs_dfs: {
              id: 'res_bfs_dfs',
              title: 'BFS vs DFS',
              url: 'https://example.com/bfs-dfs',
              type: 'article',
            },
          },
          item_order: ['item_graphs_read', 'item_graphs_drill'],
          checklist_items: {
            item_graphs_read: { id: 'item_graphs_read', text: 'Read the traversal comparison' },
            item_graphs_drill: { id: 'item_graphs_drill', text: 'Implement BFS and DFS' },
          },
        },
      },
    },
  },
  created_at: '2026-07-15T00:00:00Z',
  updated_at: '2026-07-15T00:00:00Z',
}

/** Arrays section fully done; the learner is partway into hashing (3 of 8). */
export const mockProgress: MockProgressSnapshot = {
  roadmap_id: mockRoadmap.id,
  total_items: 8,
  checked_items: 3,
  percent: 38,
  checked_ids: ['item_arrays_read', 'item_arrays_drill', 'item_hashing_read'],
  sections: [
    { section_id: 'sec_foundations', total_items: 4, checked_items: 3, percent: 75 },
    { section_id: 'sec_recursion-graphs', total_items: 4, checked_items: 0, percent: 0 },
  ],
}

export const mockOverview: MockOverview = {
  roadmap_id: mockRoadmap.id,
  title: mockRoadmap.title,
  status: mockRoadmap.status,
  revision: mockRoadmap.revision,
  sections: [
    {
      section_id: 'sec_foundations',
      title: 'Foundations',
      total_items: 4,
      checked_items: 3,
      percent: 75,
    },
    {
      section_id: 'sec_recursion-graphs',
      title: 'Recursion & graphs',
      total_items: 4,
      checked_items: 0,
      percent: 0,
    },
  ],
  overall: { total_items: 8, checked_items: 3, percent: 38 },
}

export const mockNext: MockNext = {
  items: [
    {
      subsection_id: 'sub_hashing',
      item_id: 'item_hashing_drill',
      text: 'Implement a frequency counter',
      why_now: 'Its only prerequisite (arrays & two pointers) is complete.',
      path_position: 2,
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
      id: mockRoadmap.id,
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

/** The authenticated-user shape returned by /auth/register|login|refresh. */
export const mockAuthUser: MockAuthenticatedUser = {
  id: OWNER_ID,
  username: OWNER_HANDLE,
  email: 'ada@example.com',
  created_at: '2026-07-15T00:00:00Z',
}
