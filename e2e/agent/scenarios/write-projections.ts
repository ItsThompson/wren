import type {
  CreateRoadmapDraftOutput,
  EditRoadmapMetadataOutput,
  ForkRoadmapOutput,
  McpCallToolResult,
  PatchRoadmapDraftOutput,
  PublishRoadmapOutput,
  ReplaceRoadmapDraftOutput,
  ValidateRoadmapDraftOutput,
} from './types'
import { array, booleanValue, nullableString, numberValue, record, stringArray, stringValue, structuredContent, value } from './projection-helpers'

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
