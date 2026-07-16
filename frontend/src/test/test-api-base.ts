/**
 * The API base every test harness (render wrapper + client helpers) binds to
 * unless a test overrides it. Owned here as the single source of truth so
 * `createHookWrapper`, `renderWithProviders`, and `api-clients` cannot drift to
 * different bases. Kept free of the React render graph so the client helpers can
 * import it without pulling in the provider stack.
 */
export const TEST_API_BASE = 'https://api.test'
