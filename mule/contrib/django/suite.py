# TODO: TransactionTestCase should be ordered last, and they need to completely tear down
#       all data in all tables and re-run syncdb (initial fixtures) each time.
#       This same (bad) behavior needs to happen on every TestCase if not connections_support_transactions()

from __future__ import absolute_import

from cStringIO import StringIO
from django.conf import settings
from django.db import connections, router
from django.db.backends import DatabaseProxy
from django.db.models import get_app, get_apps, get_models, signals
from django.test.simple import DjangoTestSuiteRunner, TestCase, build_suite, reorder_suite
from mule.base import Mule
from mule.runners.xml import XMLTestRunner
from mule.runners.text import TextTestRunner
from mule.utils import import_string, acquire_lock, release_lock
from optparse import make_option

import os, os.path
import signal
import sys
import types
import uuid
import unittest

LOCK_DIR = '/var/tmp'

def get_database_lock(build_id):
    # XXX: Pretty sure this needs try/except to stop race condition
    db_num = 0
    while True:
        lock_file = lock_for_database(build_id, db_num)
        try:
            acquire_lock(lock_file)
        except IOError:
            # lock unavailable
            db_num += 1
        else:
            break
    return db_num

def release_database_lock(build_id, db_num):
    lock_file = lock_for_database(build_id, db_num)
    release_lock(lock_file)

def lock_for_database(build_id, db_num=0):
    return os.path.join(LOCK_DIR, 'mule.contrib.django:db_%s_%s' % (build_id, db_num))

def build_test(label):
    """Construct a test case with the specified label. Label should be of the
    form model.TestClass or model.TestClass.test_method. Returns an
    instantiated test or test suite corresponding to the label provided.
    """
    # TODO: Refactor this as the code sucks

    imp = import_string(label)
    
    if isinstance(imp, types.ModuleType):
        return build_suite(imp)
    elif issubclass(imp, unittest.TestCase):
        return unittest.TestLoader().loadTestsFromTestCase(imp)
    elif issubclass(imp.__class__, unittest.TestCase):
        return imp.__class__(imp.__name__)

    # If no tests were found, then we were given a bad test label.
    raise ValueError("Test label '%s' does not refer to a test" % label)

def make_test_runner(parent):
    class new(parent):
        def __init__(self, verbosity=0, failfast=False, pdb=False, **kwargs):
            super(new, self).__init__(verbosity=verbosity, **kwargs)
            self.failfast = failfast
            self.pdb = pdb
            self._keyboard_interrupt_intercepted = False

        def run(self, *args, **kwargs):
            """
            Runs the test suite after registering a custom signal handler
            that triggers a graceful exit when Ctrl-C is pressed.
            """
            self._default_keyboard_interrupt_handler = signal.signal(signal.SIGINT,
                self._keyboard_interrupt_handler)
            # post_test_setup.send(sender=self.__class__, runner=self)

            try:
                result = super(new, self).run(*args, **kwargs)
            finally:
                signal.signal(signal.SIGINT, self._default_keyboard_interrupt_handler)
            return result

        def _keyboard_interrupt_handler(self, signal_number, stack_frame):
            """
            Handles Ctrl-C by setting a flag that will stop the test run when
            the currently running test completes.
            """
            self._keyboard_interrupt_intercepted = True
            sys.stderr.write(" <Test run halted by Ctrl-C> ")
            # Set the interrupt handler back to the default handler, so that
            # another Ctrl-C press will trigger immediate exit.
            signal.signal(signal.SIGINT, self._default_keyboard_interrupt_handler)

        def _makeResult(self):
            result = super(new, self)._makeResult()
            failfast = self.failfast

            def stoptest_override(func):
                def stoptest(test):
                    # If we were set to failfast and the unit test failed,
                    # or if the user has typed Ctrl-C, report and quit
                    if (failfast and not result.wasSuccessful()) or \
                        self._keyboard_interrupt_intercepted:
                        result.stop()
                    func(test)
                return stoptest

            setattr(result, 'stopTest', stoptest_override(result.stopTest))
            return result
    new.__name__ = parent.__name__
    return new

def make_suite_runner(parent):
    class new(parent):
        options = (
            make_option('--auto-bootstrap', dest='auto_bootstrap', action='store_true',
                        help='Bootstrap a new database automatically.'),
            make_option('--id', dest='build_id', help='Identifies this build within a distributed model.',
                        default='default'),
            make_option('--db-prefix', type='string', dest='db_prefix', default='test',
                        help='Prefix to use for test databases. Default is ``test``.'),
            make_option('--distributed', dest='distributed', action='store_true',
                        help='Fire test jobs off to Celery queue and collect results.'),
            make_option('--worker', dest='worker', action='store_true',
                        help='Identifies this runner as a worker of a distributed test runner.'),
        ) + getattr(parent, 'options', ())

        def __init__(self, auto_bootstrap=False, build_id='default', db_prefix='test', distributed=False, worker=False,
                     *args, **kwargs):
            super(new, self).__init__(
                verbosity=int(kwargs['verbosity']),
                failfast=kwargs['failfast'],
                interactive=kwargs['interactive'],
            )
            self.auto_bootstrap = auto_bootstrap
            self.build_id = build_id

            if self.auto_bootstrap:
                self.interactive = False

            self.db_prefix = db_prefix
            
            self.distributed = distributed
            self.worker = worker
    
        def run_suite(self, suite, output=None):
            # XXX: output is only used by XML runner, pretty ugly
            if self.worker:
                cls = XMLTestRunner
                kwargs = {
                    'output': output,
                }
            else:
                cls = TextTestRunner
                kwargs = {}

            cls = make_test_runner(cls)
        
            result = cls(verbosity=self.verbosity, failfast=self.failfast, **kwargs).run(suite)

            return result

        def build_suite(self, test_labels, extra_tests=None, **kwargs):
            suite = unittest.TestSuite()

            if test_labels:
                for label in test_labels:
                    if '.' in label:
                        suite.addTest(build_test(label))
                    else:
                        app = get_app(label)
                        suite.addTest(build_suite(app))
            else:
                for app in get_apps():
                    suite.addTest(build_suite(app))

            if extra_tests:
                for test in extra_tests:
                    suite.addTest(test)

            return reorder_suite(suite, (TestCase,))

        def setup_databases(self, *args, **kwargs):
            # We only need to setup databases if we need to bootstrap
            if self.auto_bootstrap:
                bootstrap = False
                for alias in connections:
                    if bootstrap:
                        continue
                
                    connection = connections[alias]

                    if connection.settings_dict['TEST_MIRROR']:
                        continue

                    qn = connection.ops.quote_name
                    test_database_name = connection.settings_dict['TEST_NAME']
                    cursor = connection.cursor()
                    suffix = connection.creation.sql_table_creation_suffix()
                    connection.creation.set_autocommit()

                    # HACK: this isnt an accurate check
                    try:
                        cursor.execute("CREATE DATABASE %s %s" % (qn(test_database_name), suffix))
                    except Exception, e:
                        pass
                    else:
                        bootstrap = True
                    finally:
                        cursor.close()
                    
                    connection.close()
            else:
                bootstrap = True
            
            if not bootstrap:
                # Ensure we setup ``SUPPORTS_TRANSACTIONS``
                for alias in connections:
                    connection = connections[alias]
                    if connection.settings_dict['TEST_MIRROR']:
                        mirror_alias = connection.settings_dict['TEST_MIRROR']
                        connections._connections[alias] = DatabaseProxy(connections[mirror_alias], alias)
                    else:
                        can_rollback = connection.creation._rollback_works()
                        connection.settings_dict["SUPPORTS_TRANSACTIONS"] = can_rollback
                result = None
            else:
                # HACK: We need to kill post_syncdb receivers to stop them from sending when the databases
                #       arent fully ready.
                post_syncdb_receivers = signals.post_syncdb.receivers
                signals.post_syncdb.receivers = []
                result = super(new, self).setup_databases(*args, **kwargs)
                signals.post_syncdb.receivers = post_syncdb_receivers

                for app in get_apps():
                    for db in connections:
                        all_models = [
                            [(app.__name__.split('.')[-2],
                                [m for m in get_models(app, include_auto_created=True)
                                if router.allow_syncdb(db, m)])]
                        ]
                        signals.post_syncdb.send(app=app, created_models=all_models, verbosity=self.verbosity,
                                                 db=db, sender=app, interactive=False)
            
            return result
    
        def teardown_databases(self, *args, **kwargs):
            # If we were bootstrapping we dont tear down databases
            if self.auto_bootstrap:
                return
            return super(new, self).teardown_databases(*args, **kwargs)
    
        def run_distributed_tests(self, test_labels, extra_tests=None, **kwargs):
            build_id = uuid.uuid4().hex
            mule = Mule(build_id=build_id)
            result = mule.process(test_labels, runner='python manage.py mule --auto-bootstrap --worker --id=%s #TEST#' % build_id)
            # result should now be some parseable text
            return result
        
        def run_tests(self, *args, **kwargs):
            db_num = get_database_lock(self.build_id)
            
            try:
                db_prefix = '%s_%s_%s_' % (self.db_prefix, self.build_id, db_num)

                for k, v in settings.DATABASES.iteritems():
                    # If TEST_NAME wasnt set, or we've set a non-default prefix
                    if 'TEST_NAME' not in v or self.auto_bootstrap:
                        settings.DATABASES[k]['TEST_NAME'] = db_prefix + settings.DATABASES[k]['NAME']

                self.db_prefix = db_prefix

                self._run_tests(*args, **kwargs)
            finally:
                release_database_lock(self.build_id, db_num)
        
        def _run_tests(self, test_labels, extra_tests=None, **kwargs):
            # We need to swap stdout/stderr so that the task only captures what is needed,
            # and everything else goes to our logs
            if self.worker:
                stderr, stdout = StringIO(), StringIO()
                sys_stderr, sys_stdout = sys.stderr, sys.stdout
                sys.stderr, sys.stdout = stderr, stdout
            else:
                sys_stderr, sys_stdout = sys.stderr, sys.stdout
            
            self.setup_test_environment()
            suite = self.build_suite(test_labels, extra_tests)
            
            if self.distributed:
                # we can only test whole TestCase's currently
                jobs = set(t.__class__ for t in suite._tests)
                result = self.run_distributed_tests(jobs, extra_tests=None, **kwargs)
            else:
                old_config = self.setup_databases()
                result = self.run_suite(suite, output=sys_stdout)
                self.teardown_databases(old_config)

            self.teardown_test_environment()
            
            if self.worker:
                sys.stderr, sys.stdout = sys_stderr, sys_stdout

            return self.suite_result(suite, result)

        def suite_result(self, suite, result, **kwargs):
            if self.distributed:
                return '\n'.join(result)
            return super(new, self).suite_result(suite, result, **kwargs)
    new.__name__ = parent.__name__
    return new
DjangoTestSuiteRunner = make_suite_runner(DjangoTestSuiteRunner)