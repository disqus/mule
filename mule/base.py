import os, os.path
import logging
import multiprocessing
import re
import sys
import time
import unittest
import uuid

from celery.task.control import inspect, broadcast
from celery.task.sets import TaskSet
from fnmatch import fnmatch
from mule import conf
from mule.tasks import run_test
from mule.utils.multithreading import ThreadPool

class FailFastInterrupt(KeyboardInterrupt):
    pass

def load_script(workspace, name):
    if workspace not in conf.WORKSPACES:
        return

    settings = conf.WORKSPACES[workspace]

    script_setting = settings.get(name)
    if not script_setting:
        return

    if script_setting.startswith('/'):
        with open(script_setting, 'r') as fp:
            script = fp.read()
    else:
        script = script_setting
    
    return script

class Mule(object):
    loglevel = logging.INFO
    
    def __init__(self, workspace=None, build_id=None, max_workers=None):
        if not build_id:
            build_id = uuid.uuid4().hex
        
        self.build_id = build_id
        self.max_workers = max_workers or multiprocessing.cpu_count()
        self.logger = logging.getLogger('mule')
        self.workspace = workspace
    
    def process(self, jobs, runner='unit2 $TEST', callback=None):
        """
        ``jobs`` is a list of path.to.TestCase strings to process.
        
        ``runner`` should be defined as command exectuable in bash, where $TEST is
        the current job.
        
        ``callback`` will execute a callback after each result is returned, in
        addition to return the aggregate of all results after completion.
        """
        self.logger.info("Processing build %s", self.build_id)

        self.logger.info("Provisioning (up to) %d worker(s)", self.max_workers)
        
        actual = None
        
        while not actual:
            # We need to determine which queues are available to use
            i = inspect()
            active_queues = i.active_queues() or {}
        
            if not active_queues:
                self.logger.error('No queue workers available, retrying in 1s')
                time.sleep(1)
                continue
            
            available = [host for host, queues in active_queues.iteritems() if conf.DEFAULT_QUEUE in [q['name'] for q in queues]]
        
            if not available:
                # TODO: we should probably sleep/retry (assuming there were *any* workers)
                self.logger.info('All workers are busy, retrying in 1s')
                time.sleep(1)
                continue
        
            # Attempt to provision workers which reported as available
            actual = []
            for su_response in broadcast('mule_setup',
                             arguments={'build_id': self.build_id,
                                        'workspace': self.workspace,
                                        'script': load_script(self.workspace, 'setup')},
                             destination=available[:self.max_workers],
                             reply=True,
                             timeout=0):
                for host, message in su_response.iteritems():
                    if message.get('error'):
                        self.logger.error('%s failed to setup: %s', host, message['error'])
                    elif message.get('status') == 'ok':
                        actual.append(host)
                    if message.get('stdout'):
                        self.logger.info('stdout from %s: %s', host, message['stdout'])
                    if message.get('stderr'):
                        self.logger.info('stderr from %s: %s', host, message['stderr'])
        
            if not actual:
                # TODO: we should probably sleep/retry (assuming there were *any* workers)
                self.logger.info('Failed to provision workers (busy), retrying in 1s')
                time.sleep(1)
                continue
        
        if len(actual) != len(available):
            # We should begin running tests and possibly add more, but its not a big deal
            pass

        self.logger.info('%d worker(s) were provisioned', len(actual))
            
        self.logger.info("Building queue of %d test job(s)", len(jobs))
        
        try:
            taskset = TaskSet(run_test.subtask(
                build_id=self.build_id,
                runner=runner,
                workspace=self.workspace,
                job='%s.%s' % (job.__module__, job.__name__),
                options={
                    # 'routing_key': 'mule-%s' % self.build_id,
                    'queue': 'mule-%s' % self.build_id,
                    # 'exchange': 'mule-%s' % self.build_id,
                }) for job in jobs)
            
            result = taskset.apply_async()

            self.logger.info("Waiting for response...")
            # response = result.join()
            # propagate=False ensures we get *all* responses        
            response = []
            try:
                for task_response in result.iterate():
                    response.append(task_response)
                    if callback:
                        callback(task_response)
            except KeyboardInterrupt, e:
                print '\nReceived keyboard interrupt, closing workers.\n'
        
        finally:
            self.logger.info("Tearing down %d worker(s)", len(actual))

            # Send off teardown task to all workers in pool
            for td_response in broadcast('mule_teardown',
                                        arguments={'build_id': self.build_id,
                                                   'workspace': self.workspace,
                                                   'script': load_script(self.workspace, 'teardown')},
                                        destination=actual,
                                        reply=True
                                    ):
                for host, message in td_response.iteritems():
                    if message.get('error'):
                        self.logger.error('%s failed to teardown: %s', host, message['error'])
                    if message.get('stdout'):
                        self.logger.info('stdout from %s: %s', host, message['stdout'])
                    if message.get('stderr'):
                        self.logger.info('stderr from %s: %s', host, message['stderr'])
        
        self.logger.info('Finished')
        
        return response

    def _match_path(self, path, full_path, pattern):
        # override this method to use alternative matching strategy
        return fnmatch(path, pattern)

    def _get_name_from_path(self, path, top_level_dir):
        path = os.path.splitext(os.path.normpath(path))[0]

        _relpath = os.path.relpath(path, top_level_dir)
        assert not os.path.isabs(_relpath), "Path must be within the project"
        assert not _relpath.startswith('..'), "Path must be within the project"

        name = _relpath.replace(os.path.sep, '.')
        return name

    def _get_module_from_name(self, name):
        __import__(name)
        return sys.modules[name]

    def load_tests_from_module(self, module, use_load_tests=True):
        """Return a suite of all tests cases contained in the given module"""
        tests = []
        for name in dir(module):
            obj = getattr(module, name)
            if isinstance(obj, type) and issubclass(obj, unittest.TestCase):
                tests.append(obj)

        return tests

    def discover_tests(self, start_dir, pattern='test*.py', top_level_dir=None):
        """
        Used by discovery. Yields test suites it loads.

        (Source: unittest2)
        """
        start_dir = os.path.realpath(start_dir)

        if not top_level_dir:
            top_level_dir = os.path.abspath(os.path.join(start_dir, os.pardir))
            sys.path.insert(0, start_dir)

        VALID_MODULE_NAME = re.compile(r'[_a-z]\w*\.py$', re.IGNORECASE)

        paths = os.listdir(start_dir)

        for path in paths:
            full_path = os.path.join(start_dir, path)
            if os.path.isfile(full_path):
                if not VALID_MODULE_NAME.match(path):
                    # valid Python identifiers only
                    continue
                if not self._match_path(path, full_path, pattern):
                    continue
                # if the test file matches, load it
                name = self._get_name_from_path(full_path, top_level_dir)
                try:
                    module = self._get_module_from_name(name)
                except:
                    # TODO: should this be handled more gracefully?
                    # yield _make_failed_import_test(name, self.suiteClass)
                    raise
                else:
                    mod_file = os.path.abspath(getattr(module, '__file__', full_path))
                    realpath = os.path.splitext(mod_file)[0]
                    fullpath_noext = os.path.splitext(full_path)[0]
                    if realpath.lower() != fullpath_noext.lower():
                        module_dir = os.path.dirname(realpath)
                        mod_name = os.path.splitext(os.path.basename(full_path))[0]
                        expected_dir = os.path.dirname(full_path)
                        msg = ("%r module incorrectly imported from %r. Expected %r. "
                               "Is this module globally installed?")
                        raise ImportError(msg % (mod_name, module_dir, expected_dir))
                    for test in self.load_tests_from_module(module):
                        yield test
            elif os.path.isdir(full_path):
                if not os.path.isfile(os.path.join(full_path, '__init__.py')):
                    continue

                load_tests = None
                tests = None
                if fnmatch(path, pattern):
                    # only check load_tests if the package directory itself matches the filter
                    name = self._get_name_from_path(full_path, top_level_dir)
                    package = self._get_module_from_name(name)
                    load_tests = getattr(package, 'load_tests', None)
                    tests = self.load_tests_from_module(package, use_load_tests=False)

                if tests is not None:
                    # tests loaded from package file
                    yield tests
                # recurse into the package
                for test in self.discover_tests(full_path, pattern, top_level_dir):
                    yield test

class MultiProcessMule(Mule):
    def process(self, jobs, runner='unit2 $TEST', callback=None):
        self.logger.info("Processing build %s", self.build_id)

        self.logger.info("Provisioning %d worker(s)", self.max_workers)
        
        pool = ThreadPool(self.max_workers)

        self.logger.info("Building queue of %d test job(s)", len(jobs))

        for job in jobs:
            pool.add(run_test,
                build_id=self.build_id,
                runner=runner,
                job='%s.%s' % (job.__module__, job.__name__),
                workspace=self.workspace,
                callback=callback,
            )

        self.logger.info("Waiting for response...")

        response = [r['result'] for r in pool.join()]

        self.logger.info("Tearing down %d worker(s)", self.max_workers)

        # TODO
        
        self.logger.info('Finished')
        
        return response