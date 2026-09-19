import { createHash, randomBytes } from 'node:crypto'

export interface TestAttemptIdentity {
  runId: string
  testId: string
  parallelIndex: number
  retry: number
  nonce: string
  resourcePrefix: string
}

export interface AttemptIdentityInput {
  runId?: string
  projectName: string
  file: string
  title: string
  parallelIndex: number
  retry: number
  nonce?: string
}

export interface AttemptIdentitySource {
  project: { name: string }
  file: string
  retry: number
  parallelIndex: number
  titlePath: string[]
}

export interface AttemptAccountIdentity {
  username: string
  email: string
  password: string
}

export interface RoadmapFixtureIdentity {
  title: string
  proposedIdPrefix: string
  itemIds: readonly string[]
}

export interface OAuthFixtureIdentity {
  clientName: string
  redirectUri: string
  state: string
}

export interface RecorderFixtureIdentity {
  queryIdentity: string
}

export interface AttemptResourceIdentities {
  roadmap(index?: number): RoadmapFixtureIdentity
  oauth(index: number, redirectUri: string): OAuthFixtureIdentity
  callback(index?: number): string
  recorder(index?: number): RecorderFixtureIdentity
}

const MAX_USERNAME_LENGTH = 32
const MAX_RESOURCE_LABEL_LENGTH = 120
const MAX_ROADMAP_PREFIX_LENGTH = MAX_RESOURCE_LABEL_LENGTH - '_hashing'.length
const RUN_ID_MAX_LENGTH = 64
const NONCE_LENGTH = 12

export function createAttemptIdentity(input: AttemptIdentityInput): TestAttemptIdentity {
  const runId = normalizeRunId(input.runId ?? readRunId())
  const testId = hashToken(`${input.projectName}:${input.file}:${input.title}`, 6)
  const nonce = normalizeNonce(input.nonce)
  const resourcePrefix = [
    'e2e',
    hashToken(runId, 3),
    testId,
    `w${toBase36(input.parallelIndex)}`,
    `r${toBase36(input.retry)}`,
    nonce,
  ].join('')

  return {
    runId,
    testId,
    parallelIndex: input.parallelIndex,
    retry: input.retry,
    nonce,
    resourcePrefix,
  }
}

export function createAttemptIdentityFromTestInfo(source: AttemptIdentitySource): TestAttemptIdentity {
  return createAttemptIdentity({
    projectName: source.project.name,
    file: source.file,
    title: source.titlePath.join(' > '),
    parallelIndex: source.parallelIndex,
    retry: source.retry,
  })
}

export function createAccountIdentity(
  identity: TestAttemptIdentity,
  role: string,
  index: number,
): AttemptAccountIdentity {
  const roleToken = normalizeToken(role).slice(0, 2) || 'us'
  const suffix = `${roleToken}${toBase36(index)}`
  const username = `${identity.resourcePrefix}${suffix}`.slice(0, MAX_USERNAME_LENGTH)
  return {
    username,
    email: `${username}@example.com`,
    password: 'Str0ngPass1',
  }
}

export function createRoadmapIdentity(
  identity: TestAttemptIdentity,
  index = 0,
): RoadmapFixtureIdentity {
  const indexToken = toBase36(index)
  const proposedIdPrefix = `${identity.resourcePrefix}r${indexToken}`.slice(0, MAX_ROADMAP_PREFIX_LENGTH)
  return {
    title: `E2E ${identity.resourcePrefix} roadmap ${indexToken}`.slice(0, MAX_RESOURCE_LABEL_LENGTH),
    proposedIdPrefix,
    itemIds: [
      `chk_${proposedIdPrefix}_read`.slice(0, MAX_RESOURCE_LABEL_LENGTH),
      `chk_${proposedIdPrefix}_drill`.slice(0, MAX_RESOURCE_LABEL_LENGTH),
      `chk_${proposedIdPrefix}_hash`.slice(0, MAX_RESOURCE_LABEL_LENGTH),
    ],
  }
}

export function createOAuthClientName(identity: TestAttemptIdentity, index = 0): string {
  return `e2e-${identity.resourcePrefix}-oauth-${toBase36(index)}`.slice(0, MAX_RESOURCE_LABEL_LENGTH)
}

export function createOAuthIdentity(
  identity: TestAttemptIdentity,
  index: number,
  redirectUri: string,
): OAuthFixtureIdentity {
  return {
    clientName: createOAuthClientName(identity, index),
    redirectUri,
    state: `e2e-${identity.resourcePrefix}-state-${randomBytes(12).toString('base64url')}`.slice(
      0,
      MAX_RESOURCE_LABEL_LENGTH,
    ),
  }
}

export function createAttachmentIdentifier(identity: TestAttemptIdentity, name: string): string {
  return `e2e-${identity.resourcePrefix}-${normalizeToken(name).slice(0, 16) || 'artifact'}`.slice(0, MAX_RESOURCE_LABEL_LENGTH)
}

export function createCallbackIdentity(identity: TestAttemptIdentity, index = 0): string {
  return `e2e-${identity.resourcePrefix}-callback-${toBase36(index)}`.slice(0, MAX_RESOURCE_LABEL_LENGTH)
}

export function createRecorderQueryIdentity(identity: TestAttemptIdentity, index = 0): string {
  return `e2e-${identity.resourcePrefix}-recorder-${toBase36(index)}`.slice(0, MAX_RESOURCE_LABEL_LENGTH)
}

export function createAttemptResourceIdentities(
  identity: TestAttemptIdentity,
): AttemptResourceIdentities {
  return {
    roadmap: (index = 0) => createRoadmapIdentity(identity, index),
    oauth: (index, redirectUri) => createOAuthIdentity(identity, index, redirectUri),
    callback: (index = 0) => createCallbackIdentity(identity, index),
    recorder: (index = 0) => ({ queryIdentity: createRecorderQueryIdentity(identity, index) }),
  }
}

function readRunId(): string {
  return (
    process.env.E2E_RUN_ID ??
    process.env.GITHUB_RUN_ID ??
    process.env.CI_JOB_ID ??
    `local-${process.pid}`
  )
}

function normalizeRunId(value: string): string {
  return value.trim().slice(0, RUN_ID_MAX_LENGTH) || 'local'
}

function normalizeNonce(value: string | undefined): string {
  const normalized = normalizeToken(value ?? '')
  if (normalized.length >= NONCE_LENGTH) return normalized.slice(0, NONCE_LENGTH)
  return `${normalized}${randomBytes(8).toString('hex')}`.slice(0, NONCE_LENGTH)
}

function normalizeToken(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]/g, '')
}

function hashToken(value: string, length: number): string {
  return createHash('sha256').update(value).digest('hex').slice(0, length)
}

function toBase36(value: number): string {
  if (!Number.isInteger(value) || value < 0) throw new Error('attempt indexes must be non-negative integers')
  return value.toString(36)
}
