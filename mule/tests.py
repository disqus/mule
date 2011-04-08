import os.path
import unittest2 as unittest
from mule.base import Mule
from mule.tasks import run_test

class TestRunnerTestCase(unittest.TestCase):
    def test_discovery(self):
        mule = Mule()
        jobs = list(mule.discover_tests(os.path.dirname(__file__)))
        self.assertGreater(len(jobs), 0)
        self.assertTrue('mule.tests.TestRunnerTestCase' in ['%s.%s' % (j.__module__, j.__name__) for j in jobs])

    def test_process(self):
        mule = Mule()
        result = mule.process([self.__class__], 'echo #TEST#')
        self.assertEquals(len(result), 1)
        self.assertTrue('tests.TestRunnerTestCase' in result)

class RunTestTestCase(unittest.TestCase):
    def test_subprocess(self):
        result = run_test('build_id', 'echo #TEST#', 'job')
        self.assertEquals(result, 'job')
