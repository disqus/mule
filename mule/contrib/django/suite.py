# TODO: TransactionTestCase should be ordered last, and they need to completely tear down
#       all data in all tables and re-run syncdb (initial fixtures) each time.
#       This same (bad) behavior needs to happen on every TestCase if not connections_support_transactions()

from __future__ import absolute_import

from cStringIO import StringIO
from django.conf import settings
from django.core.management import call_command
from django.db import connections, router
from django.db.backends import DatabaseProxy
from django.db.models import get_app, get_apps, get_models, signals
from django.test.simple import DjangoTestSuiteRunner, build_suite, reorder_suite
from mule.base import Mule, MultiProcessMule
from mule.runners.xml import XMLTestRunner
from mule.runners.text import TextTestRunner, _TextTestResult
from mule.utils import import_string, acquire_lock, release_lock
from optparse import make_option
from xml.dom.minidom import parseString

import os, os.path
import re
import signal
import sys
import time
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
            make_option('--multiprocess', dest='multiprocess', action='store_true',
                        help='Spawns multiple processes (controlled within threads) to test concurrently.'),
            make_option('--worker', dest='worker', action='store_true',
                        help='Identifies this runner as a worker of a distributed test runner.'),
            make_option('--xunit', dest='xunit', action='store_true',
                        help='Outputs results in XUnit format.'),
            make_option('--xunit-output', dest='xunit_output', default="./xunit/",
                        help='Specifies the output directory for XUnit results.'),
            make_option('--include', dest='include',
                        help='Specifies inclusion cases (TestCaseClassName) for the job detection.'),
            make_option('--exclude', dest='exclude',
                        help='Specifies exclusion cases (TestCaseClassName) for the job detection.'),
        ) + getattr(parent, 'options', ())

        def __init__(self, auto_bootstrap=False, build_id='default', distributed=False, worker=False,
                     multiprocess=False, *args, **kwargs):
            super(new, self).__init__(
                verbosity=int(kwargs['verbosity']),
                failfast=kwargs['failfast'],
                interactive=kwargs['interactive'],
            )
            self.auto_bootstrap = auto_bootstrap
            self.build_id = build_id

            if self.auto_bootstrap:
                self.interactive = False

            self.db_prefix = kwargs.pop('db_prefix', 'test')
            
            assert not (distributed and worker and multiprocess), "You cannot combine --distributed, --worker, and --multiprocess"
            
            self.distributed = distributed
            self.worker = worker
            self.multiprocess = multiprocess
            self.xunit = kwargs.pop('xunit', False)
            self.xunit_output = os.path.realpath(kwargs.pop('xunit_output', './xunit/'))
            if kwargs.get('include'):
                self.include_testcases = [import_string(i) for i in kwargs.pop('include').split(',')]
            else:
                self.include_testcases = None
            if kwargs.get('exclude'):
                self.exclude_testcases = [import_string(i) for i in kwargs.pop('exclude').split(',')]
            else:
                self.exclude_testcases = None
    
        def run_suite(self, suite, output=None):
            # XXX: output is only used by XML runner, pretty ugly
            if self.worker or self.xunit:
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
            
            new_suite = unittest.TestSuite()
            
            for test in reorder_suite(suite, (unittest.TestCase,)):
                if self.include_testcases and not any(isinstance(test, c) for c in self.include_testcases):
                    continue
                if self.exclude_testcases and any(isinstance(test, c) for c in self.exclude_testcases):
                    continue
                new_suite.addTest(test)

            return reorder_suite(new_suite, (unittest.TestCase,))

        def setup_databases(self, *args, **kwargs):
            # We only need to setup databases if we need to bootstrap
            if self.auto_bootstrap:
                bootstrap = False
                for alias in connections:
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
                        cursor.execute("DROP DATABASE %s" % (qn(test_database_name),))
                        bootstrap = True
                        break
                    finally:
                        cursor.close()
                    
                    connection.close()
            else:
                bootstrap = True
            
            # HACK: We need to kill post_syncdb receivers to stop them from sending when the databases
            #       arent fully ready.
            post_syncdb_receivers = signals.post_syncdb.receivers
            signals.post_syncdb.receivers = []

            if not bootstrap:
                # Ensure we setup ``SUPPORTS_TRANSACTIONS``
                old_names = []
                mirrors = []
                for alias in connections:
                    connection = connections[alias]

                    # Ensure NAME is now set to TEST_NAME
                    connection.settings_dict['NAME'] = connection.settings_dict['TEST_NAME']
                    settings.DATABASES[alias]['NAME'] = settings.DATABASES[alias]['TEST_NAME']

                    # Ensure we end up on the correct database
                    connection.close()

                    if connection.settings_dict['TEST_MIRROR']:
                        mirrors.append((alias, connection))
                        mirror_alias = connection.settings_dict['TEST_MIRROR']
                        connections._connections[alias] = DatabaseProxy(connections[mirror_alias], alias)
                    else:
                        old_names.append((connection, connection.settings_dict['NAME']))
                        can_rollback = connection.creation._rollback_works()
                        connection.settings_dict['SUPPORTS_TRANSACTIONS'] = can_rollback
                        # Clear out the existing data
                        # XXX: we can probably isolate this based on TestCase.multi_db
                        call_command('flush', verbosity=self.verbosity, interactive=self.interactive, database=alias)
            else:
                old_names, mirrors = super(new, self).setup_databases(*args, **kwargs)
            
            signals.post_syncdb.receivers = post_syncdb_receivers

            # XXX: we could truncate all tables in the teardown phase and
            #      run the syncdb steps on each iteration (to ensure compatibility w/ transactions)
            for app in get_apps():
                for db in connections:
                    all_models = [
                        [(app.__name__.split('.')[-2],
                            [m for m in get_models(app, include_auto_created=True)
                            if router.allow_syncdb(db, m)])]
                    ]
                    signals.post_syncdb.send(app=app, created_models=all_models, verbosity=self.verbosity,
                                             db=db, sender=app, interactive=False)
            
            return old_names, mirrors
    
        def teardown_databases(self, *args, **kwargs):
            # If we were bootstrapping we dont tear down databases
            if self.auto_bootstrap:
                return
            return super(new, self).teardown_databases(*args, **kwargs)
    
        def run_distributed_tests(self, test_labels, extra_tests=None, in_process=False, **kwargs):
            if in_process:
                cls = MultiProcessMule
            else:
                cls = Mule
            build_id = uuid.uuid4().hex
            mule = cls(build_id=build_id)
            result = mule.process(test_labels, runner='python manage.py mule --auto-bootstrap --worker --id=%s $TEST' % build_id)
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

                result = self._run_tests(*args, **kwargs)
            finally:
                release_database_lock(self.build_id, db_num)
            
            return result
        
        def _run_tests(self, test_labels, extra_tests=None, **kwargs):
            # We need to swap stdout/stderr so that the task only captures what is needed,
            # and everything else goes to our logs
            start = time.time()
            if self.worker:
                stderr, stdout = StringIO(), StringIO()
                sys_stderr, sys_stdout = sys.stderr, sys.stdout
                sys.stderr, sys.stdout = stderr, stdout
                output = sys_stdout
            else:
                if self.xunit:
                    output = self.xunit_output
                else:
                    output = sys.stdout
            
            self.setup_test_environment()
            suite = self.build_suite(test_labels, extra_tests)
            
            if self.distributed or self.multiprocess:
                # we can only test whole TestCase's currently
                jobs = set(t.__class__ for t in suite._tests)
                result = self.run_distributed_tests(jobs, extra_tests=None, in_process=self.multiprocess, **kwargs)
            else:
                old_config = self.setup_databases()
                try:
                    result = self.run_suite(suite, output=output)
                finally:
                    self.teardown_databases(old_config)

            self.teardown_test_environment()
            
            if self.worker:
                sys.stderr, sys.stdout = sys_stderr, sys_stdout
            
            stop = time.time()
            return self.suite_result(suite, result, stop-start)

        def suite_result(self, suite, result, total_time, **kwargs):
            if self.distributed or self.multiprocess:
                # Bootstrap our xunit output path
                if self.xunit and not os.path.exists(self.xunit_output):
                    os.makedirs(self.xunit_output)
                
                failures, errors = 0, 0
                skips, tests = 0, 0

                for r in result:
                    # XXX: stdout (which is our result) is in XML, which sucks life is easier with regexp
                    match = re.search(r'errors="(\d+)".*failures="(\d+)".*skips="(\d+)".*tests="(\d+)"', r['stdout'])
                    if match:
                        errors += int(match.group(1))
                        failures += int(match.group(2))
                        skips += int(match.group(3))
                        tests += int(match.group(4))

                    if self.xunit:
                        # Since we already get xunit results back, let's just write them to disk
                        fp = open(os.path.join(self.xunit_output, r['job'] + '.xml'), 'w')
                        try:
                            fp.write(r['stdout'])
                        finally:
                            fp.close()
                    else:
                        # HACK: Ideally we would let our default text runner represent us here, but that'd require
                        #       reconstructing the original objects which is even more of a hack
                        xml = parseString(r['stdout'])
                        for xml_test in xml.getElementsByTagName('testcase'):
                            for xml_test_res in xml_test.childNodes:
                                if xml_test_res.nodeType == xml_test_res.TEXT_NODE:
                                    continue
                                desc = xml_test_res.getAttribute('message') or '%s (%s)' % (xml_test.getAttribute('name'), xml_test.getAttribute('classname'))
                                sys.stdout.write(_TextTestResult.separator1 + '\n')
                                sys.stdout.write('%s [%.3fs]: %s\n' % \
                                    (xml_test_res.nodeName.upper(), float(xml_test.getAttribute('time') or '0.0'), desc))
                                sys.stdout.write(_TextTestResult.separator2 + '\n')
                                sys.stdout.write('%s\n' % (''.join(c.wholeText for c in xml_test_res.childNodes if c.nodeType == c.CDATA_SECTION_NODE),))
                        sys.stdout.write(_TextTestResult.separator2 + '\n')

                run = tests - skips
                sys.stdout.write("Ran %d test%s in %.3fs\n" % (run, run != 1 and "s" or "", total_time))
            
                if errors or failures or skips:
                    sys.stdout.write("FAILED (")
                    if failures:
                        sys.stdout.write("failures=%d" % failures)
                    if errors:
                        if failures:
                            sys.stdout.write(", ")
                        sys.stdout.write("errors=%d" % errors)
                    if skips:
                        if failures or errors:
                            sys.stdout.write(", ")
                        sys.stdout.write("skipped=%d" % skips)
                    sys.stdout.write(")\n")
                else:
                    sys.stdout.write("OK\n")
                
                return failures + errors
            return super(new, self).suite_result(suite, result, **kwargs)

    new.__name__ = parent.__name__

    return new

DjangoTestSuiteRunner = make_suite_runner(DjangoTestSuiteRunner)