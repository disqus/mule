from __future__ import absolute_import

from django.db.models import get_app, get_apps
from django.test.simple import DjangoTestSuiteRunner, build_suite
from django.test._doctest import DocTestCase
from mule import conf
from mule.contextmanager import register_context_manager
from mule.contrib.django.contextmanager import DatabaseContextManager, EnvContextManager
from mule.contrib.django.signals import post_test_setup
from mule.contrib.django.loader import get_test_by_name
from mule.suite import MuleTestLoader
from mule.loader import reorder_suite

import unittest
import unittest2

DEFAULT_RUNNER = 'python manage.py mule --auto-bootstrap --worker --id=$BUILD_ID $TEST'

def mule_suite_runner(parent):
    class new(MuleTestLoader, parent):
        def __init__(self, auto_bootstrap=False, db_prefix='test', runner=DEFAULT_RUNNER,
                     *args, **kwargs):
            MuleTestLoader.__init__(self, *args, **kwargs)
            parent.__init__(self,
                verbosity=int(kwargs['verbosity']),
                failfast=kwargs['failfast'],
                interactive=kwargs['interactive'],
            )
            self.auto_bootstrap = auto_bootstrap

            if self.auto_bootstrap:
                self.interactive = False

            self.db_prefix = db_prefix

            if not runner and self.workspace:
                runner = conf.WORKSPACES[self.workspace].get('runner') or DEFAULT_RUNNER

            self.base_cmd = runner or DEFAULT_RUNNER

            if self.failfast:
                self.base_cmd += ' --failfast'
            
        def run_suite(self, suite, **kwargs):
            run_callback = lambda x: post_test_setup.send(sender=type(x), runner=x)

            return MuleTestLoader.run_suite(self, suite, run_callback=run_callback, **kwargs)

        def build_suite(self, test_labels, extra_tests=None, **kwargs):
            # XXX: We shouldn't need to hook this if Mule can handle the shortname.TestCase format
            suite = unittest2.TestSuite()

            if test_labels:
                for label in test_labels:
                    if '.' in label:
                        suite.addTest(get_test_by_name(label, self.loader))
                    else:
                        app = get_app(label)
                        suite.addTest(build_suite(app))
            else:
                for app in get_apps():
                    suite.addTest(build_suite(app))

            if extra_tests:
                for test in extra_tests:
                    suite.addTest(test)
            
            new_suite = unittest2.TestSuite()
            
            for test in reorder_suite(suite, (unittest.TestCase,)):
                # XXX: Doctests (the way we do it currently) do not work
                if isinstance(test, DocTestCase):
                    continue
                if self.include_testcases and not any(isinstance(test, c) for c in self.include_testcases):
                    continue
                if self.exclude_testcases and any(isinstance(test, c) for c in self.exclude_testcases):
                    continue
                new_suite.addTest(test)

            return reorder_suite(new_suite, (unittest.TestCase,))

        def run_tests(self, *args, **kwargs):
            register_context_manager(EnvContextManager)
            
            # Ensure our db setup/teardown manager is registered
            if not (self.distributed or self.multiprocess):
                register_context_manager(DatabaseContextManager)
            
            return MuleTestLoader.run_tests(self, *args, **kwargs)
    new.__name__ = parent.__name__
    return new

DjangoTestSuiteRunner = mule_suite_runner(DjangoTestSuiteRunner)