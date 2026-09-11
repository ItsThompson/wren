import type { components } from '@/api'

export type Roadmap = components['schemas']['Roadmap']
export type RoadmapCard = components['schemas']['RoadmapCard']
export type Dashboard = components['schemas']['Dashboard']
export type Profile = components['schemas']['Profile']

export function roadmapToCard(roadmap: Roadmap): RoadmapCard {
  return {
    id: roadmap.id,
    title: roadmap.title,
    status: roadmap.status,
    visibility: roadmap.visibility,
    subject_tags: roadmap.subject_tags,
  }
}

function canAppearInFollowed(roadmap: Roadmap): boolean {
  return roadmap.visibility === 'public' && (roadmap.status === 'published' || roadmap.status === 'archived')
}

function canAppearInProfile(roadmap: Roadmap): boolean {
  return roadmap.visibility === 'public' && roadmap.status === 'published'
}

function replaceCard(cards: RoadmapCard[], roadmap: Roadmap, allowed: boolean): RoadmapCard[] {
  const index = cards.findIndex((card) => card.id === roadmap.id)
  if (!allowed) return index === -1 ? cards : cards.filter((card) => card.id !== roadmap.id)
  if (index === -1) return cards
  return cards.map((card) => (card.id === roadmap.id ? roadmapToCard(roadmap) : card))
}

export function addAuthoredRoadmap(data: Dashboard | undefined, roadmap: Roadmap): Dashboard | undefined {
  if (!data) return data
  const authored = data.authored ?? []
  if (authored.some((card) => card.id === roadmap.id)) return data
  return { ...data, authored: [roadmapToCard(roadmap), ...authored] }
}

export function reconcileDashboard(data: Dashboard | undefined, roadmap: Roadmap): Dashboard | undefined {
  if (!data) return data
  return {
    ...data,
    authored: replaceCard(data.authored ?? [], roadmap, true),
    followed: replaceCard(data.followed ?? [], roadmap, canAppearInFollowed(roadmap)),
  }
}

export function removeRoadmapFromDashboard(data: Dashboard | undefined, roadmapId: string): Dashboard | undefined {
  if (!data) return data
  return {
    ...data,
    authored: (data.authored ?? []).filter((card) => card.id !== roadmapId),
    followed: (data.followed ?? []).filter((card) => card.id !== roadmapId),
  }
}

export function reconcileProfile(data: Profile | undefined, roadmap: Roadmap): Profile | undefined {
  if (!data) return data
  const roadmaps = data.roadmaps ?? []
  const allowed = canAppearInProfile(roadmap)
  const index = roadmaps.findIndex((card) => card.id === roadmap.id)
  if (!allowed) return { ...data, roadmaps: index === -1 ? roadmaps : roadmaps.filter((card) => card.id !== roadmap.id) }
  if (index === -1) return { ...data, roadmaps: [roadmapToCard(roadmap), ...roadmaps] }
  return { ...data, roadmaps: roadmaps.map((card) => (card.id === roadmap.id ? roadmapToCard(roadmap) : card)) }
}

export function removeRoadmapFromProfile(data: Profile | undefined, roadmapId: string): Profile | undefined {
  if (!data) return data
  return { ...data, roadmaps: (data.roadmaps ?? []).filter((card) => card.id !== roadmapId) }
}
