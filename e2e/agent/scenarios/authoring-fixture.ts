export interface AuthoringRoadmapDraft {
  readonly title: string
  readonly description: string
  readonly subject_tags: readonly string[]
  readonly sections: readonly AuthoringSection[]
  readonly suggested_path: readonly string[]
}

interface AuthoringSection {
  readonly proposed_id: string
  readonly title: string
  readonly subsections: readonly AuthoringSubsection[]
}

interface AuthoringSubsection {
  readonly proposed_id: string
  readonly title: string
  readonly tags: readonly string[]
  readonly prereq_ids?: readonly string[]
  readonly resources: readonly AuthoringResource[]
  readonly checklist_items: readonly AuthoringChecklistItem[]
}

interface AuthoringResource {
  readonly proposed_id: string
  readonly title: string
  readonly url: string
  readonly type: 'article' | 'video'
}

interface AuthoringChecklistItem {
  readonly proposed_id: string
  readonly text: string
}

export function buildAuthoringRoadmap(identity: {
  readonly title: string
  readonly proposedIdPrefix: string
  readonly itemIds: readonly string[]
}): AuthoringRoadmapDraft {
  const sectionId = `${identity.proposedIdPrefix}_foundations`
  const arraysId = `${identity.proposedIdPrefix}_arrays`
  const hashingId = `${identity.proposedIdPrefix}_hashing`
  const resources = {
    arrays: {
      proposed_id: `${identity.proposedIdPrefix}_arrays_guide`,
      title: 'Arrays guide',
      url: 'https://example.com/arrays',
      type: 'article' as const,
    },
    hashing: {
      proposed_id: `${identity.proposedIdPrefix}_hashing_video`,
      title: 'Hashing video',
      url: 'https://example.com/hashing',
      type: 'video' as const,
    },
  }

  return {
    title: identity.title,
    description: 'A compact authoring journey fixture.',
    subject_tags: ['algorithms'],
    sections: [
      {
        proposed_id: sectionId,
        title: 'Foundations',
        subsections: [
          {
            proposed_id: arraysId,
            title: 'Arrays',
            tags: ['foundations'],
            resources: [resources.arrays],
            checklist_items: [
              { proposed_id: identity.itemIds[0], text: 'Read the arrays guide' },
              { proposed_id: identity.itemIds[1], text: 'Practice array traversal' },
            ],
          },
          {
            proposed_id: hashingId,
            title: 'Hashing',
            tags: ['foundations'],
            prereq_ids: [arraysId],
            resources: [resources.hashing],
            checklist_items: [{ proposed_id: identity.itemIds[2], text: 'Implement a hash table' }],
          },
        ],
      },
    ],
    suggested_path: [arraysId, hashingId],
  }
}

export function buildReplacementRoadmap(identity: {
  readonly title: string
  readonly proposedIdPrefix: string
  readonly itemIds: readonly string[]
}): AuthoringRoadmapDraft {
  const roadmap = buildAuthoringRoadmap(identity)
  const section = roadmap.sections[0]
  const arrays = section.subsections[0]
  const hashing = section.subsections[1]
  return {
    ...roadmap,
    description: 'The replaced compact authoring fixture.',
    sections: [
      {
        ...section,
        subsections: [
          { ...arrays, title: 'Arrays and strings', tags: ['foundations', 'arrays'] },
          { ...hashing, title: 'Hash tables', tags: ['foundations', 'hashing'] },
        ],
      },
    ],
  }
}

export function assertBoundedRemap(
  remap: Readonly<Record<string, string>>,
  roadmap: AuthoringRoadmapDraft,
): void {
  const proposedIds = new Set<string>()
  for (const section of roadmap.sections) {
    proposedIds.add(section.proposed_id)
    for (const subsection of section.subsections) {
      proposedIds.add(subsection.proposed_id)
      for (const resource of subsection.resources) proposedIds.add(resource.proposed_id)
      for (const item of subsection.checklist_items) proposedIds.add(item.proposed_id)
    }
  }
  const entries = Object.entries(remap)
  if (entries.length > proposedIds.size) throw new Error('roadmap remap exceeds the compact fixture node count')
  for (const [proposedId, mintedId] of entries) {
    if (!proposedIds.has(proposedId)) throw new Error(`roadmap remap contains unknown proposed ID ${proposedId}`)
    if (proposedId.length === 0 || mintedId.length === 0) throw new Error('roadmap remap IDs must be non-empty')
  }
  if (new Set(entries.map(([, mintedId]) => mintedId)).size !== entries.length) {
    throw new Error('roadmap remap values must be unique')
  }
}

export function resolveRoadmapIds(
  identity: { readonly proposedIdPrefix: string; readonly itemIds: readonly string[] },
  remap: Readonly<Record<string, string>>,
): { sectionId: string; subsectionIds: readonly string[]; itemIds: readonly string[] } {
  const sectionId = `${identity.proposedIdPrefix}_foundations`
  const subsectionIds = [
    `${identity.proposedIdPrefix}_arrays`,
    `${identity.proposedIdPrefix}_hashing`,
  ]
  return {
    sectionId: remap[sectionId] ?? sectionId,
    subsectionIds: subsectionIds.map((id) => remap[id] ?? id),
    itemIds: identity.itemIds.map((id) => remap[id] ?? id),
  }
}

export function assertRoadmapSnapshot(
  output: {
    readonly id: string
    readonly title: string
    readonly status: string
    readonly revision: number
    readonly section_order: readonly string[]
    readonly sections: Readonly<Record<string, { readonly id: string; readonly subsection_order: readonly string[] }>>
    readonly suggested_path: readonly string[]
  },
  expected: {
    id: string
    title: string
    status: string
    revision: number
    sectionId: string
    subsectionIds: readonly string[]
  },
): void {
  if (output.id !== expected.id || output.title !== expected.title || output.status !== expected.status) {
    throw new Error('roadmap read-back identity or status differs from the write')
  }
  if (output.revision !== expected.revision) throw new Error('roadmap read-back revision differs from the write')
  if (JSON.stringify(output.section_order) !== JSON.stringify([expected.sectionId])) {
    throw new Error('roadmap section order differs from the compact fixture')
  }
  const section = output.sections[expected.sectionId]
  if (section === undefined || JSON.stringify(section.subsection_order) !== JSON.stringify(expected.subsectionIds)) {
    throw new Error('roadmap subsection order differs from the compact fixture')
  }
  if (JSON.stringify(output.suggested_path) !== JSON.stringify(expected.subsectionIds)) {
    throw new Error('roadmap suggested path differs from the compact fixture')
  }
}

export function assertSubsectionTitle(
  output: { readonly section_order: readonly string[]; readonly sections: Readonly<Record<string, { readonly subsections: Readonly<Record<string, { readonly title: string }>> }>> },
  subsectionId: string,
  expectedTitle: string,
): void {
  const section = output.section_order.map((id) => output.sections[id]).find((candidate) => candidate?.subsections[subsectionId] !== undefined)
  if (section?.subsections[subsectionId]?.title !== expectedTitle) throw new Error(`subsection ${subsectionId} did not persist its changed title`)
}

export function assertSubsectionItemIds(
  output: {
    readonly section_order: readonly string[]
    readonly sections: Readonly<Record<string, { readonly subsections: Readonly<Record<string, { readonly item_order: readonly string[] }>> }>>
  },
  subsectionId: string,
  expectedItemIds: readonly string[],
): void {
  const section = output.section_order.map((id) => output.sections[id]).find((candidate) => candidate?.subsections[subsectionId] !== undefined)
  const actualItemIds = section?.subsections[subsectionId]?.item_order
  if (JSON.stringify(actualItemIds) !== JSON.stringify(expectedItemIds)) {
    throw new Error(`subsection ${subsectionId} did not persist its expected checklist identities`)
  }
}

export function assertSubsectionTags(
  output: {
    readonly section_order: readonly string[]
    readonly sections: Readonly<Record<string, { readonly subsections: Readonly<Record<string, { readonly tags: readonly string[] }>> }>>
  },
  subsectionId: string,
  expectedTags: readonly string[],
): void {
  const section = output.section_order.map((id) => output.sections[id]).find((candidate) => candidate?.subsections[subsectionId] !== undefined)
  const actualTags = section?.subsections[subsectionId]?.tags
  if (JSON.stringify(actualTags) !== JSON.stringify(expectedTags)) {
    throw new Error(`subsection ${subsectionId} did not persist its expected tags`)
  }
}

export function structureSnapshot(output: {
  readonly section_order: readonly string[]
  readonly sections: Readonly<Record<string, { readonly id: string; readonly title: string; readonly subsection_order: readonly string[]; readonly subsections: Readonly<Record<string, unknown>> }>>
  readonly suggested_path: readonly string[]
}): unknown {
  return {
    section_order: output.section_order,
    sections: output.section_order.map((sectionId) => {
      const section = output.sections[sectionId]
      return {
        id: section.id,
        title: section.title,
        subsection_order: section.subsection_order,
        subsections: section.subsection_order.map((subsectionId) => section.subsections[subsectionId]),
      }
    }),
    suggested_path: output.suggested_path,
  }
}

export function collectNodeIds(output: {
  readonly section_order: readonly string[]
  readonly sections: Readonly<Record<string, { readonly id: string; readonly subsection_order: readonly string[]; readonly subsections: Readonly<Record<string, { readonly id: string; readonly item_order: readonly string[]; readonly resource_order: readonly string[] }>> }>>
}): Set<string> {
  const ids = new Set<string>()
  for (const sectionId of output.section_order) {
    const section = output.sections[sectionId]
    ids.add(section.id)
    for (const subsectionId of section.subsection_order) {
      const subsection = section.subsections[subsectionId]
      ids.add(subsection.id)
      for (const itemId of subsection.item_order) ids.add(itemId)
      for (const resourceId of subsection.resource_order) ids.add(resourceId)
    }
  }
  return ids
}
