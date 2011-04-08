# TODO: TransactionTestCase should be ordered last, and they need to completely tear down
#       all data in all tables and re-run syncdb (initial fixtures) each time.
#       This same (bad) behavior needs to happen on every TestCase if not connections_support_transactions()

from __future__ import absolute_import

from django.conf import settings
from django.db import connections, router
from django.db.backends import DatabaseProxy
from django.db.models import get_app, get_apps, get_models, signals
from django.test.simple import DjangoTestSuiteRunner, TestCase, build_suite, reorder_suite
from mule.base import Mule
from optparse import make_option

import types
import uuid
import unittest

def import_string(import_name, silent=False):
    """Imports an object based on a string. If *silent* is True the return
    value will be None if the import fails.

    Simplified version of the function with same name from `Werkzeug`_.

    :param import_name:
        The dotted name for the object to import.
    :param silent:
        If True, import errors are ignored and None is returned instead.
    :returns:
        The imported object.
    """
    import_name = str(import_name)
    try:
        if '.' in import_name:
            module, obj = import_name.rsplit('.', 1)
            return getattr(__import__(module, None, None, [obj]), obj)
        else:
            return __import__(import_name)
    except (ImportError, AttributeError):
        if not silent:
            raise

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
    class DistributedDjangoTestSuiteRunner(parent):
        options = (
            make_option('--auto-bootstrap', dest='auto_bootstrap', action='store_true',
                        help='Bootstrap a new database automatically.'),
            make_option('--id', dest='build_id', help='Identifies this build within a distributed model.',
                        default='default'),
            make_option('--db-prefix', type='string', dest='db_prefix', default='test',
                        help='Prefix to use for test databases. Default is ``test``.'),
            make_option('--distributed', dest='distributed', action='store_true',
                        help='Fire test jobs off to Celery queue and collect results.'),
        ) + getattr(parent, 'options', ())

        def __init__(self, auto_bootstrap=False, build_id='default', db_prefix='test', distributed=False, *args, **kwargs):
            super(DistributedDjangoTestSuiteRunner, self).__init__(
                verbosity=int(kwargs['verbosity']),
                failfast=kwargs['failfast'],
                interactive=kwargs['interactive'],
            )
            self.auto_bootstrap = auto_bootstrap
            self.build_id = build_id

            db_prefix = '%s_%s_' % (db_prefix, build_id)
            
            for k, v in settings.DATABASES.iteritems():
                # If TEST_NAME wasnt set, or we've set a non-default prefix
                if 'TEST_NAME' not in v or self.auto_bootstrap:
                    settings.DATABASES[k]['TEST_NAME'] = db_prefix + settings.DATABASES[k]['NAME']

            self.db_prefix = db_prefix
    
            if self.auto_bootstrap:
                self.interactive = False
            
            self.distributed = distributed

        # def run_suite(self, suite):
        #     kwargs = {}
        #     if self.xml:
        #         cls = XMLTestRunner
        #         kwargs['output'] = settings.XML_OUTPUT
        #     else:
        #         cls = TextTestRunner
        #     cls = make_django_test_runner(cls)
        # 
        #     return cls(verbosity=self.verbosity, failfast=self.failfast, pdb=self.pdb, **kwargs).run(suite)

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
                result = super(DistributedDjangoTestSuiteRunner, self).setup_databases(*args, **kwargs)
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
            return super(DistributedDjangoTestSuiteRunner, self).teardown_databases(*args, **kwargs)
    
        def run_distributed_tests(self, test_labels, extra_tests=None, **kwargs):
            build_id = uuid.uuid4().hex
            mule = Mule()
            result = mule.process(test_labels, runner='python manage.py mtest --auto-bootstrap --id=%s #TEST#' % build_id)
            return '\n'.join(result)
        
        def run_tests(self, test_labels, extra_tests=None, **kwargs):
            self.setup_test_environment()
            suite = self.build_suite(test_labels, extra_tests)
            
            if self.distributed:
                # we can only test whole TestCase's currently
                jobs = set(t.__class__ for t in suite._tests)
                result = self.run_distributed_tests(jobs, extra_tests=None, **kwargs)
            else:
                old_config = self.setup_databases()
                result = self.run_suite(suite)
                self.teardown_databases(old_config)

            self.teardown_test_environment()

            return self.suite_result(suite, result)
    return DistributedDjangoTestSuiteRunner
DjangoTestSuiteRunner = make_test_runner(DjangoTestSuiteRunner)