/**
 * The node box dimensions, shared by the dagre layout (which must lay out
 * against the real rendered width) and the rendered {@link DagNodeCard}. Keeping
 * them in one place means the layout math and the visible card can never drift.
 * `NODE_WIDTH` is 208px = Tailwind `w-52` (13rem).
 */
export const NODE_WIDTH = 208
export const NODE_HEIGHT = 60
