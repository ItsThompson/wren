from __future__ import annotations

import unittest

from public_contracts import (
    is_authorization_server_metadata,
    is_protected_resource_metadata,
)


class PublicContractValidationTest(unittest.TestCase):
    def test_accepts_exact_authorization_metadata(self) -> None:
        self.assertTrue(
            is_authorization_server_metadata(
                {
                    "issuer": "https://api.wren.test",
                    "jwks_uri": "https://api.wren.test/jwks",
                },
                "https://api.wren.test",
            )
        )

    def test_rejects_malformed_authorization_metadata(self) -> None:
        self.assertFalse(
            is_authorization_server_metadata(
                {
                    "issuer": "https://other.example",
                    "jwks_uri": "https://other.example/jwks",
                    "description": "https://api.wren.test jwks_uri",
                },
                "https://api.wren.test",
            )
        )

    def test_accepts_exact_protected_resource_metadata(self) -> None:
        self.assertTrue(
            is_protected_resource_metadata(
                {
                    "resource": "https://mcp.wren.test",
                    "authorization_servers": ["https://api.wren.test"],
                },
                "https://mcp.wren.test",
                "https://api.wren.test",
            )
        )

    def test_rejects_malformed_protected_resource_metadata(self) -> None:
        self.assertFalse(
            is_protected_resource_metadata(
                {
                    "resource": "https://mcp.wren.test",
                    "authorization_servers": [
                        "https://api.wren.test",
                        "https://other.example",
                    ],
                },
                "https://mcp.wren.test",
                "https://api.wren.test",
            )
        )


if __name__ == "__main__":
    unittest.main()
