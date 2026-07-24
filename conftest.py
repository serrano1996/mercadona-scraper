import os
import sys

# Tests import production code as the `mercadona_scraper` package (e.g.
# `from mercadona_scraper.config import HEADERS`), so the repo root must be
# on sys.path for that package import to resolve without installing it.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
