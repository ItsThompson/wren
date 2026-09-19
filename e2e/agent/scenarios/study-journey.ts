import { OAuthScope, type AgentSession } from '../types'
import type { RoadmapFixtureIdentity, TestAttemptIdentity } from '../../fixtures/attempt-identity'
import { callScenario } from './scenario-runner'
import type {
  DashboardOutput,
  NextOutput,
  NodeOutput,
  OverviewOutput,
  ProfileOutput,
  ProgressOutput,
  ProgressUpdateOutput,
  RoadmapCardOutput,
  SearchOutput,
  SectionPageOutput,
  ToolJourneyContext,
} from './types'

export interface StudyRoadmapIdentity extends RoadmapFixtureIdentity {
  readonly roadmapId: string
  readonly ownerHandle: string
}

export interface StudyJourneyResult {
  readonly list: DashboardOutput
  readonly profile: ProfileOutput
  readonly overview: OverviewOutput
  readonly node: NodeOutput
  readonly section: SectionPageOutput
  readonly search: SearchOutput
  readonly initialProgress: ProgressOutput
  readonly initialNext: NextOutput
  readonly update: ProgressUpdateOutput
  readonly finalProgress: ProgressOutput
  readonly finalNext: NextOutput
}

export function studyScopes(): readonly OAuthScope[] {
  return [OAuthScope.ROADMAPS_READ, OAuthScope.PROGRESS_WRITE]
}

export function createStudyContext(
  agent: AgentSession,
  identity: TestAttemptIdentity,
  roadmap: StudyRoadmapIdentity,
): ToolJourneyContext {
  const sectionId = `${roadmap.proposedIdPrefix}_foundations`
  const subsectionIds = [
    `${roadmap.proposedIdPrefix}_arrays`,
    `${roadmap.proposedIdPrefix}_hashing`,
  ]
  return {
    agent,
    restSetup: {
      createAccount: async () => undefined,
      createPublishedRoadmap: async () => {
        throw new Error('study journey seeds its roadmap before the official-client flow')
      },
      readRoadmap: async () => {
        throw new Error('study journey reads persisted state through the official client')
      },
    },
    identity,
    state: {
      primaryRoadmapId: roadmap.roadmapId,
      primaryRevision: null,
      forkedRoadmapId: null,
      ownerHandle: roadmap.ownerHandle,
      sectionId,
      subsectionIds,
      itemIds: roadmap.itemIds,
      toolArguments: {},
    },
  }
}

export async function runStudyJourney(
  context: ToolJourneyContext,
  roadmap: StudyRoadmapIdentity,
): Promise<StudyJourneyResult> {
  const list = await callScenario(context, 'roadmap_list', {})
  assertPublishedCard(list.authored, roadmap)

  const profile = await callScenario(context, 'roadmap_get_profile', { handle: roadmap.ownerHandle })
  assertPublishedCard(profile.roadmaps, roadmap)

  const overview = await callScenario(context, 'roadmap_get_overview', {
    roadmap_id: roadmap.roadmapId,
  })
  assertOverviewCounts(overview, context)

  const node = await callScenario(context, 'roadmap_get_node', {
    roadmap_id: roadmap.roadmapId,
    subsection_id: context.state.subsectionIds[1],
    format: 'detailed',
  })
  assertNodeDetails(node, context)

  const section = await callScenario(context, 'roadmap_get_section', {
    roadmap_id: roadmap.roadmapId,
    section_id: context.state.sectionId,
    include: 'both',
  })
  assertSectionPage(section, context)

  const search = await callScenario(context, 'roadmap_search', {
    roadmap_id: roadmap.roadmapId,
    query: 'hash',
  })
  assertSearchHit(search, context)

  const initialProgress = await callScenario(context, 'progress_get', {
    roadmap_id: roadmap.roadmapId,
    detailed: true,
  })
  assertInitialProgress(initialProgress, roadmap)

  const initialNext = await callScenario(context, 'roadmap_get_next', {
    roadmap_id: roadmap.roadmapId,
    format: 'detailed',
  })
  assertNextItems(initialNext, roadmap.itemIds.slice(0, 2), 2)

  const update = await callScenario(context, 'progress_update', {
    roadmap_id: roadmap.roadmapId,
    item_ids: roadmap.itemIds.slice(0, 2),
    state: 'complete',
  })
  if (update.progress.checked_items !== 2 || update.progress.checked_ids?.length !== 2) {
    throw new Error('progress_update did not persist the first subsection items')
  }
  assertNextItems(update.next, [roadmap.itemIds[2]], 1)

  const finalProgress = await callScenario(context, 'progress_get', {
    roadmap_id: roadmap.roadmapId,
    detailed: true,
  })
  if (
    finalProgress.checked_items !== 2 ||
    JSON.stringify((finalProgress.checked_ids ?? []).slice().sort()) !== JSON.stringify(roadmap.itemIds.slice(0, 2).sort())
  ) {
    throw new Error('progress_get did not observe the persisted checked state')
  }

  const finalNext = await callScenario(context, 'roadmap_get_next', {
    roadmap_id: roadmap.roadmapId,
    format: 'detailed',
  })
  assertNextItems(finalNext, [roadmap.itemIds[2]], 1)

  return { list, profile, overview, node, section, search, initialProgress, initialNext, update, finalProgress, finalNext }
}

function assertPublishedCard(cards: readonly RoadmapCardOutput[], roadmap: StudyRoadmapIdentity): void {
  const card = cards.find((candidate) => candidate.id === roadmap.roadmapId)
  if (card === undefined) throw new Error(`study roadmap ${roadmap.roadmapId} is missing from the read surface`)
  if (card.title !== roadmap.title || card.status !== 'published' || card.published_visibility !== 'public') {
    throw new Error('study roadmap card has unexpected identity or lifecycle state')
  }
}

function assertOverviewCounts(output: OverviewOutput, context: ToolJourneyContext): void {
  if (
    output.roadmap_id !== context.state.primaryRoadmapId ||
    output.status !== 'published' ||
    output.overall.total_items !== context.state.itemIds.length ||
    output.overall.checked_items !== 0 ||
    output.overall.percent !== 0
  ) {
    throw new Error('roadmap overview does not report the stable initial study counts')
  }
  const section = output.sections.find((candidate) => candidate.section_id === context.state.sectionId)
  if (section === undefined || section.total_items !== context.state.itemIds.length || section.checked_items !== 0) {
    throw new Error('roadmap overview does not report the expected section counts')
  }
}

function assertNodeDetails(output: NodeOutput, context: ToolJourneyContext): void {
  const expectedSubsectionId = context.state.subsectionIds[1]
  if (output.subsection_id !== expectedSubsectionId || output.items.length !== 1) {
    throw new Error('node read does not identify the prerequisite subsection and checklist item')
  }
  if (output.items[0].id !== context.state.itemIds[2] || output.prereqs.length !== 1) {
    throw new Error('node read does not return stable checklist and prerequisite identities')
  }
  if (output.prereqs[0].id !== context.state.subsectionIds[0] || output.prereqs[0].done) {
    throw new Error('node read has an unexpected prerequisite state')
  }
  if (output.resources.length === 0 || output.resources.some((resource) => !resource.url.startsWith('https://'))) {
    throw new Error('node read must return HTTPS resource links')
  }
}

function assertSectionPage(output: SectionPageOutput, context: ToolJourneyContext): void {
  if (output.section_id !== context.state.sectionId || output.include !== 'both' || output.next_cursor !== null) {
    throw new Error('section read does not return the requested identity, include mode, or cursor shape')
  }
  const subsectionIds = output.subsections.map((subsection) => subsection.subsection_id)
  if (JSON.stringify(subsectionIds) !== JSON.stringify(context.state.subsectionIds)) {
    throw new Error('section read does not preserve subsection order')
  }
}

function assertSearchHit(output: SearchOutput, context: ToolJourneyContext): void {
  const expectedSubsectionId = context.state.subsectionIds[1]
  const hit = output.hits.find((candidate) => candidate.subsection_id === expectedSubsectionId)
  if (
    hit === undefined ||
    !['subsection', 'item'].includes(hit.kind) ||
    (!hit.title_or_text.toLowerCase().includes('hash') && !hit.matched_tags?.includes('hashing'))
  ) {
    throw new Error('roadmap search does not return a stable matching hit')
  }
}

function assertInitialProgress(output: ProgressOutput, roadmap: StudyRoadmapIdentity): void {
  if (
    output.roadmap_id !== roadmap.roadmapId ||
    output.total_items !== roadmap.itemIds.length ||
    output.checked_items !== 0 ||
    output.percent !== 0 ||
    output.deadline !== null ||
    JSON.stringify(output.checked_ids) !== JSON.stringify([])
  ) {
    throw new Error('progress_get does not report the expected initial state')
  }
}

function assertNextItems(output: NextOutput, expectedItemIds: readonly string[], remainingInPath: number): void {
  if (
    output.complete ||
    output.remaining_in_path !== remainingInPath ||
    JSON.stringify(output.items.map((item) => item.item_id)) !== JSON.stringify(expectedItemIds)
  ) {
    throw new Error('roadmap_get_next does not report the expected study path')
  }
}
