"""Optional sharding for the fixture test files (TASK-308): STEM_TEST_SHARD=i/n runs every n-th test (0-based i), so
stem-check.py can run shards of one file in parallel. Without the variable all tests run as with unittest.main()."""
import os, sys, unittest

# TASK-430: every test file imports this module, so a local test run and its subprocesses never fire usage probes (docs/agent/PROBES.md)
os.environ["STEM_TEST"] = "1"


def main(verbosity=1):
    spec = os.environ.get("STEM_TEST_SHARD")
    if not spec:
        unittest.main(module="__main__", verbosity=verbosity)  # as before: honors test names given on the command line
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules["__main__"])
    if spec:
        i, n = (int(x) for x in spec.split("/"))
        tests = []
        def flat(s):
            for t in s:
                flat(t) if isinstance(t, unittest.TestSuite) else tests.append(t)
        flat(suite)
        suite = unittest.TestSuite(t for k, t in enumerate(tests) if k % n == i)
    res = unittest.TextTestRunner(verbosity=verbosity).run(suite)
    sys.exit(0 if res.wasSuccessful() else 1)
