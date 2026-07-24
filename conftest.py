import os
import sys

# The project uses bare top-level imports (e.g. `from config import HEADERS`),
# so the repo root must be on sys.path for tests to import production modules
# the same way the production code imports each other.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
