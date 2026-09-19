import type {
  CreateRoadmapDraftOutput,
  DashboardOutput,
  EditRoadmapMetadataOutput,
  ForkRoadmapOutput,
  ItemStateOutput,
  McpCallToolResult,
  NextItemOutput,
  NextOutput,
  NodeOutput,
  OverviewDetailsOutput,
  OverviewOutput,
  PatchRoadmapDraftOutput,
  PrereqOutput,
  ProfileOutput,
  ProgressOutput,
  ProgressUpdateOutput,
  PublishRoadmapOutput,
  ReplaceRoadmapDraftOutput,
  ResourceLinkOutput,
  ResourceOutput,
  RoadmapCardOutput,
  RoadmapOutput,
  RoadmapSectionDocumentOutput,
  SearchHitOutput,
  SearchOutput,
  SectionOverviewOutput,
  SectionPageOutput,
  ValidateRoadmapDraftOutput,
} from './types'

type StructuredContent = Record<string, unknown>
type ValueParser<T> = (value: unknown, field: string) => T

function structuredContent(result: McpCallToolResult): StructuredContent {
  if (result.isError === true) throw new Error('MCP tool returned an error result')
  return record(result.structuredContent, 'structuredContent')
}

function record(value: unknown, field: string): StructuredContent {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new Error(`${field} must be an object`)
  }
  return value as StructuredContent
}

function stringValue(value: unknown, field: string): string {
  if (typeof value !== 'string') throw new Error(`${field} must be a string`)
  return value
}

function numberValue(value: unknown, field: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) throw new Error(`${field} must be a finite number`)
  return value
}

function booleanValue(value: unknown, field: string): boolean {
  if (typeof value !== 'boolean') throw new Error(`${field} must be a boolean`)
  return value
}

function nullableString(value: unknown, field: string): string | null {
  if (value === null) return null
  return stringValue(value, field)
}

function value<T>(source: StructuredContent, field: string, parser: ValueParser<T>): T {
  return parser(source[field], field)
}

function array<T>(valueToParse: unknown, field: string, parser: ValueParser<T>): T[] {
  if (!Array.isArray(valueToParse)) throw new Error(`${field} must be an array`)
  return valueToParse.map((item, index) => parser(item, `${field}[${index}]`))
}

function stringArray(valueToParse: unknown, field: string): string[] {
  return array(valueToParse, field, stringValue)
}

function objectMap<T>(valueToParse: unknown, field: string, parser: ValueParser<T>): Record<string, T> {
  const source = record(valueToParse, field)
  return Object.fromEntries(Object.entries(source).map(([key, item]) => [key, parser(item, `${field}.${key}`)]))
}

function card(valueToParse: unknown, field: string): RoadmapCardOutput {
  const source = record(valueToParse, field)
  return {
    id: value(source, 'id', stringValue),
    published_visibility: value(source, 'published_visibility', stringValue),
    status: value(source, 'status', stringValue),
    subject_tags: value(source, 'subject_tags', stringArray),
    title: value(source, 'title', stringValue),
  }
}

function resourceLink(valueToParse: unknown, field: string): ResourceLinkOutput {
  const source = record(valueToParse, field)
  return {
    title: value(source, 'title', stringValue),
    url: value(source, 'url', stringValue),
    type: value(source, 'type', stringValue),
  }
}

function nextItem(valueToParse: unknown, field: string): NextItemOutput {
  const source = record(valueToParse, field)
  const pathPosition = source.path_position
  return {
    item_id: value(source, 'item_id', stringValue),
    path_position: pathPosition === null ? null : numberValue(pathPosition, `${field}.path_position`),
    resources: array(source.resources, `${field}.resources`, resourceLink),
    subsection_id: value(source, 'subsection_id', stringValue),
    text: value(source, 'text', stringValue),
    why_now: value(source, 'why_now', stringValue),
  }
}

export function projectDashboard(result: McpCallToolResult): DashboardOutput {
  const source = structuredContent(result)
  return {
    authored: value(source, 'authored', (item, field) => array(item, field, card)),
    followed: value(source, 'followed', (item, field) => array(item, field, card)),
  }
}

export function projectProfile(result: McpCallToolResult): ProfileOutput {
  const source = structuredContent(result)
  return {
    display_name: value(source, 'display_name', stringValue),
    handle: value(source, 'handle', stringValue),
    roadmaps: value(source, 'roadmaps', (item, field) => array(item, field, card)),
  }
}

function roadmapSection(valueToParse: unknown, field: string): RoadmapSectionDocumentOutput {
  const source = record(valueToParse, field)
  return {
    id: value(source, 'id', stringValue),
    subsection_order: value(source, 'subsection_order', stringArray),
    subsections: value(source, 'subsections', (item, itemField) => objectMap(item, itemField, (entry) => record(entry, itemField))),
    title: value(source, 'title', stringValue),
  }
}

export function projectRoadmap(result: McpCallToolResult): RoadmapOutput {
  const source = structuredContent(result)
  return {
    created_at: value(source, 'created_at', stringValue),
    description: value(source, 'description', nullableString),
    id: value(source, 'id', stringValue),
    owner: value(source, 'owner', stringValue),
    published_visibility: value(source, 'published_visibility', stringValue),
    revision: value(source, 'revision', numberValue),
    section_order: value(source, 'section_order', stringArray),
    sections: value(source, 'sections', (item, field) => objectMap(item, field, roadmapSection)),
    status: value(source, 'status', stringValue),
    subject_tags: value(source, 'subject_tags', stringArray),
    suggested_path: value(source, 'suggested_path', stringArray),
    title: value(source, 'title', stringValue),
    updated_at: value(source, 'updated_at', stringValue),
  }
}

function sectionOverview(valueToParse: unknown, field: string): SectionOverviewOutput {
  const source = record(valueToParse, field)
  return {
    section_id: value(source, 'section_id', stringValue),
    title: value(source, 'title', stringValue),
    total_items: value(source, 'total_items', numberValue),
    checked_items: value(source, 'checked_items', numberValue),
    percent: value(source, 'percent', numberValue),
  }
}

function overallProgress(valueToParse: unknown, field: string) {
  const source = record(valueToParse, field)
  return {
    total_items: value(source, 'total_items', numberValue),
    checked_items: value(source, 'checked_items', numberValue),
    percent: value(source, 'percent', numberValue),
  }
}

function overviewDetails(valueToParse: unknown, field: string): OverviewDetailsOutput {
  const source = record(valueToParse, field)
  return {
    owner: value(source, 'owner', stringValue),
    description: value(source, 'description', nullableString),
    subject_tags: value(source, 'subject_tags', stringArray),
    published_visibility: value(source, 'published_visibility', stringValue),
    created_at: value(source, 'created_at', stringValue),
    updated_at: value(source, 'updated_at', stringValue),
    suggested_path: value(source, 'suggested_path', stringArray),
  }
}

export function projectOverview(result: McpCallToolResult): OverviewOutput {
  const source = structuredContent(result)
  return {
    details: source.details === null ? null : overviewDetails(source.details, 'details'),
    overall: value(source, 'overall', overallProgress),
    revision: value(source, 'revision', numberValue),
    roadmap_id: value(source, 'roadmap_id', stringValue),
    sections: value(source, 'sections', (item, field) => array(item, field, sectionOverview)),
    status: value(source, 'status', stringValue),
    title: value(source, 'title', stringValue),
  }
}

function nextOutput(source: StructuredContent, _field: string): NextOutput {
  return {
    complete: value(source, 'complete', booleanValue),
    items: value(source, 'items', (item, itemField) => array(item, itemField, nextItem)),
    remaining_in_path: value(source, 'remaining_in_path', numberValue),
  }
}

export function projectNext(result: McpCallToolResult): NextOutput {
  return nextOutput(structuredContent(result), 'structuredContent')
}

function itemState(valueToParse: unknown, field: string): ItemStateOutput {
  const source = record(valueToParse, field)
  return {
    id: value(source, 'id', stringValue),
    text: value(source, 'text', stringValue),
    done: value(source, 'done', booleanValue),
  }
}

function prereq(valueToParse: unknown, field: string): PrereqOutput {
  const source = record(valueToParse, field)
  return {
    id: value(source, 'id', stringValue),
    title: value(source, 'title', stringValue),
    done: value(source, 'done', booleanValue),
  }
}

function resource(valueToParse: unknown, field: string): ResourceOutput {
  const source = record(valueToParse, field)
  return {
    id: value(source, 'id', stringValue),
    title: value(source, 'title', stringValue),
    url: value(source, 'url', stringValue),
    type: value(source, 'type', stringValue),
  }
}

function node(valueToParse: unknown, field: string): NodeOutput {
  const source = record(valueToParse, field)
  return {
    description: value(source, 'description', nullableString),
    effort_estimate: value(source, 'effort_estimate', nullableString),
    items: value(source, 'items', (item, itemField) => array(item, itemField, itemState)),
    prereqs: value(source, 'prereqs', (item, itemField) => array(item, itemField, prereq)),
    resources: value(source, 'resources', (item, itemField) => array(item, itemField, resource)),
    subsection_id: value(source, 'subsection_id', stringValue),
    tags: value(source, 'tags', stringArray),
    title: value(source, 'title', stringValue),
  }
}

export function projectNode(result: McpCallToolResult): NodeOutput {
  return node(structuredContent(result), 'structuredContent')
}

export function projectSection(result: McpCallToolResult): SectionPageOutput {
  const source = structuredContent(result)
  return {
    include: value(source, 'include', stringValue),
    next_cursor: value(source, 'next_cursor', nullableString),
    section_id: value(source, 'section_id', stringValue),
    steering: value(source, 'steering', nullableString),
    subsections: value(source, 'subsections', (item, field) => array(item, field, node)),
    title: value(source, 'title', stringValue),
  }
}

function searchHit(valueToParse: unknown, field: string): SearchHitOutput {
  const source = record(valueToParse, field)
  const matchedTags = source.matched_tags
  return {
    item_id: source.item_id === null ? null : stringValue(source.item_id, `${field}.item_id`),
    kind: value(source, 'kind', stringValue),
    matched_tags: matchedTags === null ? null : stringArray(matchedTags, `${field}.matched_tags`),
    subsection_id: value(source, 'subsection_id', stringValue),
    title_or_text: value(source, 'title_or_text', stringValue),
  }
}

export function projectSearch(result: McpCallToolResult): SearchOutput {
  const source = structuredContent(result)
  return { hits: value(source, 'hits', (item, field) => array(item, field, searchHit)) }
}

function sectionProgress(valueToParse: unknown, field: string) {
  const source = record(valueToParse, field)
  return {
    section_id: value(source, 'section_id', stringValue),
    total_items: value(source, 'total_items', numberValue),
    checked_items: value(source, 'checked_items', numberValue),
    percent: value(source, 'percent', numberValue),
  }
}

function progress(valueToParse: unknown, field: string): ProgressOutput {
  const source = record(valueToParse, field)
  return {
    roadmap_id: value(source, 'roadmap_id', stringValue),
    total_items: value(source, 'total_items', numberValue),
    checked_items: value(source, 'checked_items', numberValue),
    percent: value(source, 'percent', numberValue),
    deadline: value(source, 'deadline', nullableString),
    sections: value(source, 'sections', (item, itemField) => array(item, itemField, sectionProgress)),
    checked_ids: source.checked_ids === null ? null : stringArray(source.checked_ids, `${field}.checked_ids`),
  }
}

export function projectProgress(result: McpCallToolResult): ProgressOutput {
  return progress(structuredContent(result), 'structuredContent')
}

export function projectProgressUpdate(result: McpCallToolResult): ProgressUpdateOutput {
  const source = structuredContent(result)
  return {
    progress: value(source, 'progress', progress),
    next: value(source, 'next', (item, field) => nextOutput(record(item, field), field)),
  }
}

function mutation(result: McpCallToolResult): { roadmap_id: string; revision: number; status: string } {
  const source = structuredContent(result)
  return {
    roadmap_id: value(source, 'roadmap_id', stringValue),
    revision: value(source, 'revision', numberValue),
    status: value(source, 'status', stringValue),
  }
}

function remap(valueToParse: unknown, field: string): Readonly<Record<string, string>> {
  const source = record(valueToParse, field)
  return Object.fromEntries(Object.entries(source).map(([key, item]) => [key, stringValue(item, `${field}.${key}`)]))
}

export function projectCreate(result: McpCallToolResult): CreateRoadmapDraftOutput {
  const source = structuredContent(result)
  return { ...mutation(result), remap: value(source, 'remap', remap) }
}

export function projectPatch(result: McpCallToolResult): PatchRoadmapDraftOutput {
  const source = structuredContent(result)
  return {
    ...mutation(result),
    changed_nodes: value(source, 'changed_nodes', (item, field) => array(item, field, (entry, entryField) => record(entry, entryField))),
    remap: value(source, 'remap', remap),
  }
}

export function projectReplace(result: McpCallToolResult): ReplaceRoadmapDraftOutput {
  const source = structuredContent(result)
  return { ...mutation(result), remap: value(source, 'remap', remap) }
}

export function projectValidate(result: McpCallToolResult): ValidateRoadmapDraftOutput {
  const source = structuredContent(result)
  return {
    publishable: value(source, 'publishable', booleanValue),
    violations: value(source, 'violations', (item, field) => array(item, field, (entry, entryField) => record(entry, entryField))),
  }
}

export function projectPublish(result: McpCallToolResult): PublishRoadmapOutput {
  return mutation(result)
}

export function projectFork(result: McpCallToolResult): ForkRoadmapOutput {
  const source = structuredContent(result)
  return { ...mutation(result), source_roadmap_id: value(source, 'source_roadmap_id', stringValue) }
}

export function projectMetadata(result: McpCallToolResult): EditRoadmapMetadataOutput {
  const source = structuredContent(result)
  return {
    roadmap_id: value(source, 'roadmap_id', stringValue),
    title: value(source, 'title', stringValue),
    description: value(source, 'description', nullableString),
    subject_tags: value(source, 'subject_tags', stringArray),
  }
}
