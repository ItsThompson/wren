/**
 * Shapes for the MSW dev fixtures (`src/mocks/data.ts`). These are dev-harness
 * test doubles that approximate the section 04 read projections and the section
 * 06 REST responses; they are NOT the API contract. The real request/response
 * types come from `just codegen` (`src/api/schema.d.ts`) once the backend routes
 * land, at which point handlers can be typed against the generated client.
 */

export type RoadmapStatus = 'draft' | 'published' | 'archived'
export type Visibility = 'public' | 'private'
export type ResourceType =
  | 'article'
  | 'video'
  | 'book'
  | 'course'
  | 'doc'
  | 'exercise'

export interface MockResource {
  type: ResourceType
  title: string
  url: string
}

export interface MockChecklistItem {
  id: string
  text: string
}

/** A subsection ("node"): track tags are hash-colored via lib/tag-color.ts. */
export interface MockSubsection {
  id: string
  title: string
  track_tags: string[]
  effort: string
  prereq_ids: string[]
  resources: MockResource[]
  checklist_items: MockChecklistItem[]
}

export interface MockSection {
  id: string
  title: string
  /** Subsection ids in `suggested_path` order within this section. */
  subsection_order: string[]
  subsections: MockSubsection[]
}

export interface MockRoadmap {
  id: string
  title: string
  description: string
  subject_tags: string[]
  status: RoadmapStatus
  visibility: Visibility
  owner_handle: string
  revision: number
  /** Ordered subsection ids across the whole roadmap. */
  suggested_path: string[]
  sections: MockSection[]
}

export interface MockSectionProgress {
  section_id: string
  completed: number
  total: number
}

export interface MockProgressSnapshot {
  roadmap_id: string
  checked_item_ids: string[]
  overall_completed: number
  overall_total: number
  sections: MockSectionProgress[]
}

export interface MockOverviewSection {
  id: string
  title: string
  progress: MockSectionProgress
}

export interface MockOverview {
  id: string
  title: string
  subject_tags: string[]
  overall_completed: number
  overall_total: number
  sections: MockOverviewSection[]
}

export interface MockNextItem {
  subsection_id: string
  item_id: string
  title: string
  why_now: string
}

export interface MockNext {
  roadmap_id: string
  items: MockNextItem[]
  remaining_in_path: number
  complete: boolean
}

export interface MockRoadmapCard {
  id: string
  title: string
  status: RoadmapStatus
  visibility: Visibility
  subject_tags: string[]
}

export interface MockDashboard {
  authored: MockRoadmapCard[]
  followed: MockRoadmapCard[]
}

export interface MockProfile {
  handle: string
  display_name: string
  roadmaps: MockRoadmapCard[]
}

export interface MockProgressUpdateResult {
  progress: MockProgressSnapshot
  next: MockNext
}
