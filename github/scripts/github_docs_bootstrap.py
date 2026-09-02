"""Compatibility imports for persisted v1 docs-bootstrap callers.

New integrations must import :mod:`github_docs_journey`.  The journey module
continues to read and reconcile v1 records until they are terminal.
"""

import sys

import github_docs_journey as _journey

# Preserve monkey-patching and process recovery behavior for legacy callers:
# ``github_docs_bootstrap`` is the same module object, not a copied namespace.
sys.modules[__name__] = _journey
