import os.path
import unittest2 as unittest
from mule.runner import TestRunner
from mule.tasks import run_test

class TestRunnerTestCase(unittest.TestCase):
    def test_discovery(self):
        runner = TestRunner()
        jobs = list(runner.discover_tests(os.path.dirname(__file__)))
        self.assertGreater(len(jobs), 0)
        self.assertTrue('mule.tests.TestRunnerTestCase' in ['%s.%s' % (j.__module__, j.__name__) for j in jobs])

    def test_process(self):
        runner = TestRunner()
        result = runner.process('echo #TEST#', os.path.dirname(__file__))
        self.assertGreater(len(result), 0)
        self.assertTrue('mule.tests.TestRunnerTestCase' in result)

class RunTestTestCase(unittest.TestCase):
    def test_subprocess(self):
        result = run_test('build_id', 'echo #TEST#', 'job')
        self.assertEquals(result, 'job')
