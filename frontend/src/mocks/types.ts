import type { components } from '@/api'

/**
 * Shapes for the MSW dev fixtures (`src/mocks/data.ts`). These now alias the
 * OpenAPI-generated schema (`src/api/schema.d.ts`) directly, so the zero-backend
 * dev harness (`npm run dev:mock`) serves exactly the response shapes
 * the views consume. Kept as `Mock*` aliases so the handlers/fixtures read as the
 * dev doubles they are, while staying pinned to the real contract (drift-gated by
 * codegen in CI).
 */
export type MockRoadmap = components['schemas']['Roadmap']
export type MockProgressSnapshot = components['schemas']['ProgressSnapshot']
export type MockNext = components['schemas']['NextResult']
export type MockOverview = components['schemas']['Overview']
export type MockDashboard = components['schemas']['Dashboard']
export type MockProfile = components['schemas']['Profile']
export type MockProgressUpdateResult = components['schemas']['ProgressUpdateResult']
export type MockAuthenticatedUser = components['schemas']['AuthenticatedUser']
