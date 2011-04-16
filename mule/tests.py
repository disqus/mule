import os.path
from unittest2 import TestCase
from dingus import Dingus
from mule.base import Mule
from mule import conf
from mule.tasks import run_test, mule_provision, mule_teardown

def dingus_calls_to_dict(obj):
    # remap dingus calls into a useable dict
    calls = {}
    for name, args, kwargs, obj in obj:
        if name not in calls:
            calls[name] = []
        calls[name].append((args, kwargs, obj))
    return calls

class TestRunnerTestCase(TestCase):
    def test_discovery(self):
        mule = Mule()
        jobs = list(mule.discover_tests(os.path.dirname(__file__)))
        self.assertGreater(len(jobs), 0)
        self.assertTrue('mule.tests.TestRunnerTestCase' in ['%s.%s' % (j.__module__, j.__name__) for j in jobs])

    # def test_process(self):
    #     # TODO: process() needs broken down so it can be better tested
    #     mule = Mule()
    #     result = mule.process([self.__class__], 'echo $TEST')
    #     self.assertEquals(len(result), 1)
    #     result = result[0]
    #     self.assertTrue('retcode' in result)
    #     self.assertTrue('timeStarted' in result)
    #     self.assertTrue('timeFinished' in result)
    #     self.assertTrue('build_id' in result)
    #     self.assertTrue('stdout' in result)
    #     self.assertTrue('stderr' in result)
    #     self.assertTrue('job' in result)
    #     self.assertEquals(result['job'], 'tests.TestRunnerTestCase')
    #     self.assertEquals(result['stdout'], 'tests.TestRunnerTestCase')
    #     self.assertGreater(result['timeFinished'], result['timeStarted'])

class RunTestTestCase(TestCase):
    def test_subprocess(self):
        result = run_test('build_id', 'echo $TEST', 'job')
        self.assertTrue('retcode' in result)
        self.assertTrue('timeStarted' in result)
        self.assertTrue('timeFinished' in result)
        self.assertTrue('build_id' in result)
        self.assertTrue('stdout' in result)
        self.assertTrue('stderr' in result)
        self.assertTrue('job' in result)
        self.assertEquals(result['job'], 'job')
        self.assertEquals(result['stdout'], 'job')
        self.assertGreater(result['timeFinished'], result['timeStarted'])

    def test_callback(self):
        bar = []
        def foo(result):
            bar.append(result)
        
        result = run_test('build_id', 'echo $TEST', 'job', foo)
        self.assertEquals(len(bar), 1)
        result = bar[0]
        self.assertTrue('retcode' in result)
        self.assertTrue('timeStarted' in result)
        self.assertTrue('timeFinished' in result)
        self.assertTrue('build_id' in result)
        self.assertTrue('stdout' in result)
        self.assertTrue('stderr' in result)
        self.assertTrue('job' in result)
        self.assertEquals(result['job'], 'job')
        self.assertEquals(result['stdout'], 'job')
        self.assertGreater(result['timeFinished'], result['timeStarted'])

class PanelTestCase(TestCase):
    def test_provision(self):
        panel = Dingus('Panel')
        result = mule_provision(panel, 1)

        self.assertEquals(result, {
            "status": "fail",
            "reason": "worker is already in use"
        })

        # Ensure we're now in the default queue
        queue = Dingus('Queue')
        queue.name = conf.DEFAULT_QUEUE
        panel.consumer.task_consumer.queues = [queue]
        result = mule_provision(panel, 1)

        self.assertEquals(result, {
            "status": "ok",
            "build_id": 1,
        })
        
        calls = dingus_calls_to_dict(panel.consumer.task_consumer.calls)
                
        self.assertTrue('cancel_by_queue' in calls)
        self.assertTrue(len(calls['cancel_by_queue']), 1)
        call = calls['cancel_by_queue'][0]
        self.assertTrue(len(call[0]), 1)
        self.assertTrue(call[0][0], conf.DEFAULT_QUEUE)

        self.assertTrue('consume' in calls)
        self.assertTrue(len(calls['consume']), 1)
        
        self.assertTrue('add_consumer_from_dict' in calls)
        self.assertTrue(len(calls['add_consumer_from_dict']), 1)
        call = calls['add_consumer_from_dict'][0]
        self.assertTrue('queue' in call[1])
        self.assertEquals(call[1]['queue'], '%s-1' % conf.BUILD_QUEUE_PREFIX)

    def test_teardown(self):
        panel = Dingus('Panel')
        result = mule_teardown(panel, 1)

        self.assertEquals(result, {
            "status": "ok",
            "build_id": 1,
        })
        
        calls = dingus_calls_to_dict(panel.consumer.task_consumer.calls)
                
        self.assertTrue('cancel_by_queue' in calls)
        self.assertTrue(len(calls['cancel_by_queue']), 1)
        call = calls['cancel_by_queue'][0]
        self.assertTrue(len(call[0]), 1)
        self.assertTrue(call[0][0], '%s-1' % conf.BUILD_QUEUE_PREFIX)

        self.assertTrue('consume' in calls)
        self.assertTrue(len(calls['consume']), 1)
        
        self.assertTrue('add_consumer_from_dict' in calls)
        self.assertTrue(len(calls['add_consumer_from_dict']), 1)
        call = calls['add_consumer_from_dict'][0]
        self.assertTrue('queue' in call[1])
        self.assertEquals(call[1]['queue'], conf.DEFAULT_QUEUE)