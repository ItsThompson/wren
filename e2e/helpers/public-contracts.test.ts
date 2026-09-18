import { expect, test } from 'vitest'

import {
  isAuthorizationServerMetadata,
  isProtectedResourceMetadata,
} from './public-contracts.ts'

test('accepts authorization metadata with the canonical issuer and JWKS URI', () => {
  expect(
    isAuthorizationServerMetadata(
      { issuer: 'https://api.wren.test', jwks_uri: 'https://api.wren.test/jwks' },
      'https://api.wren.test',
    ),
  ).toBe(true)
})

test('rejects authorization metadata with expected values in unrelated fields', () => {
  expect(
    isAuthorizationServerMetadata(
      {
        issuer: 'https://other.example',
        jwks_uri: 'https://other.example/jwks',
        description: 'https://api.wren.test jwks_uri',
      },
      'https://api.wren.test',
    ),
  ).toBe(false)
})

test('accepts only the exact protected-resource metadata shape', () => {
  expect(
    isProtectedResourceMetadata(
      {
        resource: 'https://mcp.wren.test',
        authorization_servers: ['https://api.wren.test'],
      },
      'https://mcp.wren.test',
      'https://api.wren.test',
    ),
  ).toBe(true)
})

test('rejects protected-resource metadata with extra or misplaced authorization servers', () => {
  expect(
    isProtectedResourceMetadata(
      {
        resource: 'https://mcp.wren.test',
        authorization_servers: ['https://other.example', 'https://api.wren.test'],
        note: 'https://api.wren.test',
      },
      'https://mcp.wren.test',
      'https://api.wren.test',
    ),
  ).toBe(false)
})
