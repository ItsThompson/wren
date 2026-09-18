import assert from 'node:assert/strict'
import test from 'node:test'

import {
  isAuthorizationServerMetadata,
  isProtectedResourceMetadata,
} from './public-contracts.ts'

void test('accepts authorization metadata with the canonical issuer and JWKS URI', () => {
  assert.equal(
    isAuthorizationServerMetadata(
      { issuer: 'https://api.wren.test', jwks_uri: 'https://api.wren.test/jwks' },
      'https://api.wren.test',
    ),
    true,
  )
})

void test('rejects authorization metadata with expected values in unrelated fields', () => {
  assert.equal(
    isAuthorizationServerMetadata(
      {
        issuer: 'https://other.example',
        jwks_uri: 'https://other.example/jwks',
        description: 'https://api.wren.test jwks_uri',
      },
      'https://api.wren.test',
    ),
    false,
  )
})

void test('accepts only the exact protected-resource metadata shape', () => {
  assert.equal(
    isProtectedResourceMetadata(
      {
        resource: 'https://mcp.wren.test',
        authorization_servers: ['https://api.wren.test'],
      },
      'https://mcp.wren.test',
      'https://api.wren.test',
    ),
    true,
  )
})

void test('rejects protected-resource metadata with extra or misplaced authorization servers', () => {
  assert.equal(
    isProtectedResourceMetadata(
      {
        resource: 'https://mcp.wren.test',
        authorization_servers: ['https://other.example', 'https://api.wren.test'],
        note: 'https://api.wren.test',
      },
      'https://mcp.wren.test',
      'https://api.wren.test',
    ),
    false,
  )
})
