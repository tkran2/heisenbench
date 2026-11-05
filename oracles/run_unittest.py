"""Run a target's unittest suite from tests/, optionally excluding named tests.

Usage: python run_unittest.py [--exclude TEST_NAME ...]   (run from the target checkout)

Used for RunLedger, whose oversized-request HTTP test races its own server: the server
answers 413 before draining the request body, so the client sometimes gets a broken
pipe instead (about 1 run in 20 locally, nearly always on GitHub's runners). The test
exercises HTTP request limits, not anything the bug library touches.
"""

import argparse
import sys
import unittest


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


ap = argparse.ArgumentParser()
ap.add_argument("--exclude", nargs="*", default=[])
args = ap.parse_args()
sys.path.insert(0, ".")
tests = [t for t in flatten(unittest.defaultTestLoader.discover("tests")) if not any(x in t.id() for x in args.exclude)]
result = unittest.TextTestRunner(verbosity=1).run(unittest.TestSuite(tests))
sys.exit(0 if result.wasSuccessful() else 1)
