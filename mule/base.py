import os, os.path
import logging
import re
import sys
import unittest
import uuid

from celery.task.sets import TaskSet
from fnmatch import fnmatch
from mule.tasks import run_test

class Mule(object):
    loglevel = logging.INFO
    
    def __init__(self, build_id=None):
        if not build_id:
            build_id = uuid.uuid4().hex
        
        self.build_id = build_id
        
        self.logger = logging.getLogger('mule')
    
    def process(self, jobs, runner='unit2 #TEST#'):
        self.logger.info("Processing build %s", self.build_id)

        self.logger.info("Building queue of %d test jobs", len(jobs))
        
        taskset = TaskSet(run_test.subtask(
            build_id=self.build_id,
            runner=runner,
            job='%s.%s' % (job.__module__, job.__name__)) for job in jobs)
        result = taskset.apply_async()

        self.logger.info("Waiting for response...")
        response = result.join()
        # propagate=False ensures we get *all* responses
        # response = result.join(propagate=False)
        
        self.logger.info('finished')
        
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
