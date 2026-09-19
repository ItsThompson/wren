import { createServer, type Server } from 'node:http'

import type { TestAttemptIdentity } from './attempt-identity'
import { createCallbackIdentity } from './attempt-identity'
import type { AsyncResource, ContextOwner } from './context-owner'

export interface CallbackListener extends AsyncResource {
  callbackIdentity: string
  callbackUrl: string
  waitForCallback(timeoutMs?: number): Promise<URL>
}

export async function createCallbackListener(
  identity: TestAttemptIdentity,
  owner: ContextOwner,
  index = 0,
): Promise<CallbackListener> {
  const callbackIdentity = createCallbackIdentity(identity, index)
  let resolveCallback: (callbackUrl: URL) => void = () => undefined
  const callbackPromise = new Promise<URL>((resolve) => {
    resolveCallback = resolve
  })
  const server = createServer((request, response) => {
    const requestUrl = new URL(request.url ?? '/', `http://${request.headers.host ?? '127.0.0.1'}`)
    if (requestUrl.pathname !== '/callback') {
      response.writeHead(404)
      response.end()
      return
    }
    response.writeHead(200, { 'content-type': 'text/plain' })
    response.end('callback received')
    resolveCallback(requestUrl)
  })

  await listen(server)
  const address = server.address()
  if (address === null || typeof address === 'string') {
    await closeServer(server)
    throw new Error('callback listener did not receive an ephemeral port')
  }

  const listener: CallbackListener = {
    name: `callback-listener-${callbackIdentity}`,
    callbackIdentity,
    callbackUrl: `http://127.0.0.1:${address.port}/callback`,
    waitForCallback(timeoutMs = 5_000): Promise<URL> {
      return Promise.race([
        callbackPromise,
        new Promise<URL>((_, reject) => {
          const timeout = setTimeout(() => reject(new Error('callback listener timed out')), timeoutMs)
          timeout.unref()
        }),
      ])
    },
    close: () => closeServer(server),
  }
  owner.own(listener)
  return listener
}

function listen(server: Server): Promise<void> {
  return new Promise((resolve, reject) => {
    const handleError = (error: Error): void => {
      server.off('listening', handleListening)
      reject(error)
    }
    const handleListening = (): void => {
      server.off('error', handleError)
      resolve()
    }
    server.once('error', handleError)
    server.once('listening', handleListening)
    server.listen(0, '127.0.0.1')
  })
}

function closeServer(server: Server): Promise<void> {
  if (!server.listening) return Promise.resolve()
  return new Promise((resolve, reject) => {
    server.close((error) => {
      if (error !== undefined) reject(error)
      else resolve()
    })
  })
}
