"""Test configuration.

The fault harness lives at the repository root, outside the control plane
(ARCHITECTURE.md §3), so that injection code can never be imported by the
shipped package. The tests do need it, so the repo root goes on sys.path here
rather than making `harness` a dependency of `kavach`.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
