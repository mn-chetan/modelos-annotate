"""Global pytest configuration for backend tests.

Ensures test runs execute against an isolated test database so that
running pytest never pollutes the development database.
"""

from __future__ import annotations

import os

# Set isolated test database parameters before any application modules are loaded
os.environ["MONGODB_DATABASE"] = "ingenii_annotate_test"
os.environ["DEBUG"] = "false"
