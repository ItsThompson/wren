import { toProblem } from '@/lib/problem'

/** The base shape every `openapi-fetch` result satisfies (success or error). */
export type OpenApiResultBase = { data?: unknown; error?: unknown; response: Response }

/**
 * A success/error union for a specific success body `T`, mirroring
 * `openapi-fetch`'s `FetchResponse`: `data` is present only on the ok branch and
 * `error` (the parsed problem+json body) only on the failure branch. Used to
 * author typed results (tests, fakes); real calls infer their own result type
 * straight from `client.GET(path)`.
 */
export type OpenApiResult<T> =
  | { data: T; error?: undefined; response: Response }
  | { data?: undefined; error: unknown; response: Response }

/**
 * The typed success body carried by an `openapi-fetch` result union `R`.
 * Distributes over the success/error union so the error branch contributes
 * nothing, leaving exactly the ok-branch body. This is what lets `runQuery` and
 * the query hooks infer `data` from a `client.GET(path)` thunk with no cast at
 * the call site (the error branch would otherwise leak `undefined` into `T`).
 */
export type SuccessData<R extends OpenApiResultBase> = R extends { data?: infer D }
  ? Exclude<D, undefined>
  : never

/**
 * Turn one `openapi-fetch` call into SWR's throw-based model. `openapi-fetch`
 * never throws on an HTTP error (it resolves to `{ error }`); SWR keys its error
 * state off a *thrown* value, so this is the single seam that reconciles the two
 * and the only piece every read and every optimistic mutate shares.
 *
 * - returns the typed success body when the response is ok and there is no error
 * - throws `toProblem(error, response)` on an error body or a non-ok response
 * - normalizes a network rejection (`fetch` throws, no `Response`) to a thrown
 *   `Problem` with `status: null`, so every value thrown from the seam is a
 *   `Problem` and the hooks' `error` stays typed
 *
 * The thunk is invoked exactly once; `runQuery` never touches raw `fetch`.
 */
export async function runQuery<R extends OpenApiResultBase>(
  call: () => Promise<R>,
): Promise<SuccessData<R>> {
  let result: R
  try {
    result = await call()
  } catch (cause) {
    // `openapi-fetch` rethrows fetch rejections it cannot handle (network down,
    // DNS, CORS): the call rejects with no Response. There is no status to read.
    throw toProblem(cause, null)
  }

  const { data, error, response } = result
  if (error || !response.ok) throw toProblem(error, response)
  // Safe: on an ok response with no error body `openapi-fetch` guarantees `data`
  // is the typed success body. The `ok` guard is the runtime narrowing the type
  // system cannot see; this is the single boundary cast.
  return data as SuccessData<R>
}
