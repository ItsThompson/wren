"""Cross-domain test support layer.

Houses fixtures and test doubles consumed by more than one domain's tests, so
shared fakes are not co-located under a single domain dir where another domain
reaches across.
"""
