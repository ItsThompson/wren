import { expect, type Page } from '@playwright/test'

import type { RoadmapOutput, ToolJourneyState } from '../agent/scenarios/types'

export interface StudyChecklistItem {
  readonly id: string
  readonly text: string
}

export interface AgentStudyJourneyState {
  readonly roadmapId: string
  readonly title: string
  readonly firstSubsectionId: string
  readonly firstSubsectionTitle: string
  readonly secondSubsectionId: string
  readonly secondSubsectionTitle: string
  readonly prerequisiteItems: readonly [StudyChecklistItem, StudyChecklistItem]
  readonly finalItem: StudyChecklistItem
  readonly deadlineIso: string
}

export function createAgentStudyJourneyState(
  roadmap: RoadmapOutput,
  journeyState: Pick<ToolJourneyState, 'subsectionIds' | 'itemIds'>,
  deadlineIso: string,
): AgentStudyJourneyState {
  const [firstSubsectionId, secondSubsectionId] = journeyState.subsectionIds
  const [firstItemId, secondItemId, finalItemId] = journeyState.itemIds
  if (
    firstSubsectionId === undefined ||
    secondSubsectionId === undefined ||
    firstItemId === undefined ||
    secondItemId === undefined ||
    finalItemId === undefined
  ) {
    throw new Error('official roadmap state must contain two subsections and three checklist items')
  }

  const firstSubsection = findSubsection(roadmap, firstSubsectionId)
  const secondSubsection = findSubsection(roadmap, secondSubsectionId)
  const prerequisiteItems = [
    findChecklistItem(firstSubsection, firstItemId),
    findChecklistItem(firstSubsection, secondItemId),
  ] as const
  const finalItem = findChecklistItem(secondSubsection, finalItemId)

  return {
    roadmapId: roadmap.id,
    title: roadmap.title,
    firstSubsectionId,
    firstSubsectionTitle: firstSubsection.title,
    secondSubsectionId,
    secondSubsectionTitle: secondSubsection.title,
    prerequisiteItems,
    finalItem,
    deadlineIso,
  }
}

export async function openRoadmapFromDashboard(page: Page, state: AgentStudyJourneyState): Promise<void> {
  await page.goto('/dashboard')
  await expect(page.getByRole('heading', { name: 'Yours' })).toBeVisible()
  const roadmapLink = page.getByRole('link', { name: state.title, exact: true })
  await expect(roadmapLink).toHaveAttribute('href', `/roadmaps/${state.roadmapId}`)
  await roadmapLink.click()
  await expect(page).toHaveURL(new RegExp(`/roadmaps/${escapeRegExp(state.roadmapId)}$`))
  await expect(page.getByRole('heading', { level: 1, name: state.title })).toBeVisible()
}

export async function setRoadmapDeadline(page: Page, state: AgentStudyJourneyState): Promise<void> {
  const deadlineControl = page.getByLabel('Deadline', { exact: true })
  await Promise.all([
    page.waitForResponse((response) => {
      const url = new URL(response.url())
      return (
        response.request().method() === 'PUT' &&
        url.pathname === `/roadmaps/${state.roadmapId}/deadline` &&
        response.status() === 200
      )
    }),
    deadlineControl.fill(state.deadlineIso),
  ])
  await expect(deadlineControl).toHaveValue(state.deadlineIso)
}

export async function toggleChecklistItem(
  page: Page,
  item: StudyChecklistItem,
  checked: boolean,
  roadmapId: string,
): Promise<void> {
  const checkbox = page.getByRole('checkbox', { name: item.text, exact: true })
  const expectedState = checked ? 'complete' : 'incomplete'
  await Promise.all([
    page.waitForResponse((response) => {
      const url = new URL(response.url())
      return (
        response.request().method() === 'POST' &&
        url.pathname === `/roadmaps/${roadmapId}/progress` &&
        response.status() === 200
      )
    }),
    expectedState === 'complete' ? checkbox.check() : checkbox.uncheck(),
  ])
  await expect(checkbox).toBeChecked({ checked })
}

export async function expectOverallProgress(page: Page, percent: number): Promise<void> {
  await expect(page.getByRole('progressbar', { name: 'Overall progress' })).toHaveAttribute(
    'aria-valuenow',
    String(percent),
  )
}

export async function openRoadmapView(page: Page, view: 'List' | 'Tree'): Promise<void> {
  await page.getByRole('link', { name: view, exact: true }).click()
  const suffix = view === 'Tree' ? '/tree$' : '$'
  await expect(page).toHaveURL(new RegExp(`/roadmaps/[^/]+${suffix}`))
}

export async function expectTreeNodeState(
  page: Page,
  title: string,
  state: 'locked' | 'available' | 'done',
): Promise<void> {
  const node = page.getByRole('link', { name: `${title} (${state})`, exact: true })
  await expect(node).toBeVisible()
  await expect(node).toHaveAttribute('data-state', state)
}

export async function reloadStudyState(
  page: Page,
  state: AgentStudyJourneyState,
  checkedItems: readonly StudyChecklistItem[],
): Promise<void> {
  await page.reload()
  await expect(page.getByLabel('Deadline', { exact: true })).toHaveValue(state.deadlineIso)
  const checkedItemIds = new Set(checkedItems.map((item) => item.id))
  for (const item of [...state.prerequisiteItems, state.finalItem]) {
    await expect(page.getByRole('checkbox', { name: item.text, exact: true })).toBeChecked({
      checked: checkedItemIds.has(item.id),
    })
  }
}

function findSubsection(roadmap: RoadmapOutput, subsectionId: string) {
  for (const sectionId of roadmap.section_order) {
    const subsection = roadmap.sections[sectionId]?.subsections[subsectionId]
    if (subsection !== undefined) return subsection
  }
  throw new Error(`official roadmap response did not contain subsection ${subsectionId}`)
}

function findChecklistItem(
  subsection: ReturnType<typeof findSubsection>,
  itemId: string,
): StudyChecklistItem {
  const item = subsection.checklist_items[itemId]
  if (item === undefined) throw new Error(`official roadmap response did not contain checklist item ${itemId}`)
  return { id: item.id, text: item.text }
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

export interface RoadmapMetadata {
  title: string
  description: string
  subjectTags: string
}

export async function editRoadmapDetails(page: Page, metadata: RoadmapMetadata): Promise<void> {
  await page.getByRole('button', { name: 'Edit details' }).click()
  const editor = page.getByRole('form', { name: 'Edit roadmap details' })
  await editor.getByLabel('Title').fill(metadata.title)
  await editor.getByLabel('Description').fill(metadata.description)
  await editor.getByLabel('Subject tags').fill(metadata.subjectTags)
  await editor.getByRole('button', { name: 'Save details' }).click()
  await expect(editor).not.toBeVisible()
  await expect(page.getByRole('heading', { level: 1, name: metadata.title })).toBeVisible()
  await expect(page.getByText(metadata.description, { exact: true })).toBeVisible()
  for (const tag of metadata.subjectTags.split(',').map((value) => value.trim())) {
    await expect(page.getByText(tag, { exact: true })).toBeVisible()
  }
}

export async function publishRoadmap(page: Page): Promise<void> {
  await page.getByRole('button', { name: 'Publish' }).click()
  await expect(page.getByText('Public access', { exact: true })).toBeVisible()
}

export async function setRoadmapVisibility(page: Page, visibility: 'public' | 'private'): Promise<void> {
  const currentLabel = visibility === 'public' ? 'Private access' : 'Public access'
  const nextLabel = visibility === 'public' ? 'Public access' : 'Private access'
  await page.getByRole('button', { name: currentLabel }).click()
  await expect(page.getByRole('button', { name: nextLabel })).toBeVisible()
}

export async function forkRoadmap(page: Page): Promise<string> {
  await page.getByRole('button', { name: 'Fork' }).click()
  await expect(page).toHaveURL(/\/roadmaps\/[^/]+$/)
  await expect(page.getByText('Draft · preview', { exact: true })).toBeVisible()
  const roadmapId = new URL(page.url()).pathname.split('/').pop()
  if (!roadmapId) throw new Error('Fork navigation did not include a roadmap ID')
  return roadmapId
}

export async function archiveRoadmap(page: Page): Promise<void> {
  await page.getByRole('button', { name: 'Archive' }).click()
  await page.getByRole('button', { name: 'Confirm archive' }).click()
  await expect(page.getByText('Archived', { exact: true })).toBeVisible()
  await expect(page.getByText(/hidden from discovery/i)).toBeVisible()
}

export async function deleteRoadmap(page: Page): Promise<void> {
  await page.getByRole('button', { name: 'Delete' }).click()
  await page.getByRole('button', { name: 'Confirm delete' }).click()
  await expect(page).toHaveURL(/\/$/)
}
