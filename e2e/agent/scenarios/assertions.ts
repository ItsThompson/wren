import type {
  DashboardOutput,
  EditRoadmapMetadataOutput,
  ForkRoadmapOutput,
  NextOutput,
  NodeOutput,
  OverviewOutput,
  PatchRoadmapDraftOutput,
  ProfileOutput,
  ProgressOutput,
  ProgressUpdateOutput,
  RoadmapOutput,
  SearchOutput,
  SectionPageOutput,
  ToolJourneyContext,
  ValidateRoadmapDraftOutput,
} from './types'

const ROADMAP_STATUSES = new Set(['draft', 'published', 'archived'])
const PUBLISHED_VISIBILITIES = new Set(['public', 'private'])
const SECTION_INCLUDES = new Set(['subsections', 'items', 'both'])
const SEARCH_KINDS = new Set(['subsection', 'item'])

function fail(message: string): never {
  throw new Error(`MCP tool stable assertion failed: ${message}`)
}

function requireCondition(condition: boolean, message: string): void {
  if (!condition) fail(message)
}

function assertStatus(status: string, field: string): void {
  requireCondition(ROADMAP_STATUSES.has(status), `${field} has an invalid status`)
}

function assertRoadmapId(roadmapId: string, context: ToolJourneyContext): void {
  const expectedRoadmapId = context.state.primaryRoadmapId
  if (expectedRoadmapId !== null) requireCondition(roadmapId === expectedRoadmapId, `roadmap_id must be ${expectedRoadmapId}`)
}

function assertRoadmapIdentity(roadmapId: string, revision: number, context: ToolJourneyContext): void {
  assertRoadmapId(roadmapId, context)
  const previousRevision = context.state.primaryRevision
  if (previousRevision !== null) requireCondition(revision >= previousRevision, 'revision must not move backwards')
}

function assertRoadmapCard(card: DashboardOutput['authored'][number]): void {
  requireCondition(card.id.length > 0, 'roadmap card id must not be empty')
  requireCondition(card.title.length > 0, 'roadmap card title must not be empty')
  assertStatus(card.status, 'roadmap card status')
  requireCondition(PUBLISHED_VISIBILITIES.has(card.published_visibility), 'roadmap card visibility is invalid')
}

export function assertDashboard(output: DashboardOutput, context: ToolJourneyContext): Promise<void> {
  const cards = [...output.authored, ...output.followed]
  for (const card of cards) assertRoadmapCard(card)
  const expectedRoadmapId = context.state.primaryRoadmapId
  if (expectedRoadmapId !== null) {
    requireCondition(cards.some((card) => card.id === expectedRoadmapId), `dashboard must contain ${expectedRoadmapId}`)
  }
  return Promise.resolve()
}

export function assertProfile(output: ProfileOutput, context: ToolJourneyContext): Promise<void> {
  const requestedHandle = context.state.toolArguments?.roadmap_get_profile?.handle
  const expectedHandle = typeof requestedHandle === 'string' ? requestedHandle : context.state.ownerHandle
  requireCondition(output.handle === expectedHandle, `profile handle must be ${expectedHandle}`)
  for (const card of output.roadmaps) assertRoadmapCard(card)
  const expectedRoadmapId = context.state.primaryRoadmapId
  if (expectedRoadmapId !== null) requireCondition(output.roadmaps.some((card) => card.id === expectedRoadmapId), `profile must contain ${expectedRoadmapId}`)
  return Promise.resolve()
}

export function assertRoadmap(output: RoadmapOutput, context: ToolJourneyContext): Promise<void> {
  assertRoadmapIdentity(output.id, output.revision, context)
  requireCondition(output.title.length > 0, 'roadmap title must not be empty')
  assertStatus(output.status, 'roadmap status')
  requireCondition(output.section_order.every((sectionId) => output.sections[sectionId]?.id === sectionId), 'section order must resolve to section identities')
  return Promise.resolve()
}

export function assertOverview(output: OverviewOutput, context: ToolJourneyContext): Promise<void> {
  assertRoadmapIdentity(output.roadmap_id, output.revision, context)
  requireCondition(output.title.length > 0, 'overview title must not be empty')
  assertStatus(output.status, 'overview status')
  requireCondition(output.overall.checked_items <= output.overall.total_items, 'overall checked count exceeds total')
  for (const section of output.sections) {
    requireCondition(section.checked_items <= section.total_items, `section ${section.section_id} checked count exceeds total`)
  }
  if (context.state.sectionId !== null) requireCondition(output.sections.some((section) => section.section_id === context.state.sectionId), `overview must contain ${context.state.sectionId}`)
  return Promise.resolve()
}

export function assertNext(output: NextOutput, context: ToolJourneyContext): Promise<void> {
  requireCondition(output.remaining_in_path >= 0, 'remaining_in_path must not be negative')
  for (const item of output.items) {
    requireCondition(item.item_id.length > 0, 'next item id must not be empty')
    requireCondition(item.subsection_id.length > 0, 'next subsection id must not be empty')
    requireCondition(item.why_now.length > 0, 'next item why_now must not be empty')
  }
  if (context.state.itemIds.length > 0 && output.items.length > 0) {
    requireCondition(context.state.itemIds.includes(output.items[0].item_id), 'next item must belong to the attempt fixture')
  }
  return Promise.resolve()
}

export function assertNode(output: NodeOutput, context: ToolJourneyContext): Promise<void> {
  const requestedSubsectionId = context.state.toolArguments?.roadmap_get_node?.subsection_id
  if (typeof requestedSubsectionId === 'string') requireCondition(output.subsection_id === requestedSubsectionId, 'node identity differs from request')
  if (context.state.subsectionIds.length > 0) requireCondition(context.state.subsectionIds.includes(output.subsection_id), 'node is outside the attempt fixture')
  if (context.state.itemIds.length > 0) {
    requireCondition(output.items.every((item) => context.state.itemIds.includes(item.id)), 'node item is outside the attempt fixture')
  }
  return Promise.resolve()
}

export function assertSection(output: SectionPageOutput, context: ToolJourneyContext): Promise<void> {
  const requestedSectionId = context.state.toolArguments?.roadmap_get_section?.section_id
  if (typeof requestedSectionId === 'string') requireCondition(output.section_id === requestedSectionId, 'section identity differs from request')
  if (context.state.sectionId !== null) requireCondition(output.section_id === context.state.sectionId, 'section is outside the attempt fixture')
  requireCondition(SECTION_INCLUDES.has(output.include), 'section include has an invalid value')
  if (context.state.subsectionIds.length > 0) {
    requireCondition(output.subsections.every((subsection) => context.state.subsectionIds.includes(subsection.subsection_id)), 'section node is outside the attempt fixture')
  }
  return Promise.resolve()
}

export function assertSearch(output: SearchOutput, context: ToolJourneyContext): Promise<void> {
  requireCondition(output.hits.length > 0, 'search must return a stable hit')
  for (const hit of output.hits) {
    requireCondition(SEARCH_KINDS.has(hit.kind), 'search hit kind is invalid')
    requireCondition(hit.subsection_id.length > 0, 'search hit subsection id must not be empty')
  }
  if (context.state.subsectionIds.length > 0) requireCondition(context.state.subsectionIds.includes(output.hits[0].subsection_id), 'search hit is outside the attempt fixture')
  return Promise.resolve()
}

export function assertProgress(output: ProgressOutput, context: ToolJourneyContext): Promise<void> {
  if (context.state.primaryRoadmapId !== null) requireCondition(output.roadmap_id === context.state.primaryRoadmapId, 'progress roadmap must match the primary roadmap')
  requireCondition(output.checked_items <= output.total_items, 'checked count exceeds total')
  requireCondition(output.percent >= 0 && output.percent <= 100, 'progress percent is outside 0..100')
  if (context.state.itemIds.length === 0) requireCondition(output.checked_items === 0, 'initial progress must be empty')
  if (output.checked_ids !== null && context.state.itemIds.length > 0) {
    requireCondition(output.checked_ids.every((itemId) => context.state.itemIds.includes(itemId)), 'progress item is outside the attempt fixture')
  }
  return Promise.resolve()
}

export function assertProgressUpdate(output: ProgressUpdateOutput, context: ToolJourneyContext): Promise<void> {
  return assertProgress(output.progress, context).then(() => assertNext(output.next, context))
}

function assertMutationIdentity(output: { roadmap_id: string; revision: number; status: string }, context: ToolJourneyContext): void {
  assertRoadmapIdentity(output.roadmap_id, output.revision, context)
  assertStatus(output.status, 'mutation status')
}

export function assertCreate(output: { roadmap_id: string; revision: number; status: string }, _context: ToolJourneyContext): Promise<void> {
  requireCondition(output.revision === 1, 'created roadmap revision must be 1')
  requireCondition(output.status === 'draft', 'created roadmap must be a draft')
  requireCondition(output.roadmap_id.length > 0, 'created roadmap id must not be empty')
  return Promise.resolve()
}

export function assertPatch(output: PatchRoadmapDraftOutput, context: ToolJourneyContext): Promise<void> {
  assertRoadmapId(output.roadmap_id, context)
  if (context.state.primaryRevision !== null) requireCondition(output.revision > context.state.primaryRevision, 'patch must advance revision')
  return Promise.resolve()
}

export function assertReplace(output: { roadmap_id: string; revision: number; status: string }, context: ToolJourneyContext): Promise<void> {
  assertMutationIdentity(output, context)
  if (context.state.primaryRevision !== null) requireCondition(output.revision > context.state.primaryRevision, 'replace must advance revision')
  return Promise.resolve()
}

export function assertValidate(output: ValidateRoadmapDraftOutput, _context: ToolJourneyContext): Promise<void> {
  requireCondition(output.publishable === (output.violations.length === 0), 'publishable must match violations')
  return Promise.resolve()
}

export function assertPublish(output: { roadmap_id: string; revision: number; status: string }, context: ToolJourneyContext): Promise<void> {
  assertMutationIdentity(output, context)
  requireCondition(output.status === 'published', 'published roadmap must have published status')
  return Promise.resolve()
}

export function assertFork(output: ForkRoadmapOutput, context: ToolJourneyContext): Promise<void> {
  const primaryRoadmapId = context.state.primaryRoadmapId
  if (primaryRoadmapId !== null) {
    requireCondition(output.roadmap_id !== primaryRoadmapId, 'fork must return a distinct roadmap id')
    requireCondition(output.source_roadmap_id === primaryRoadmapId, 'fork source must match the primary roadmap')
  }
  requireCondition(output.source_roadmap_id.length > 0, 'fork source id must not be empty')
  requireCondition(output.revision === 1 && output.status === 'draft', 'fork must return a fresh draft')
  return Promise.resolve()
}

export function assertMetadata(output: EditRoadmapMetadataOutput, context: ToolJourneyContext): Promise<void> {
  assertRoadmapId(output.roadmap_id, context)
  requireCondition(output.title.length > 0, 'metadata title must not be empty')
  const requested = context.state.toolArguments?.edit_roadmap_metadata
  if (requested !== undefined) {
    if (typeof requested.title === 'string') requireCondition(output.title === requested.title, 'metadata title differs from request')
    if (requested.description !== undefined) requireCondition(output.description === requested.description, 'metadata description differs from request')
    if (Array.isArray(requested.subject_tags)) requireCondition(JSON.stringify(output.subject_tags) === JSON.stringify(requested.subject_tags), 'metadata tags differ from request')
  }
  return Promise.resolve()
}

