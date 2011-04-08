from __future__ import absolute_import

from django.conf import settings
from django.db import connections, router
from django.db.models import get_apps, get_models, signals
from django.test.simple import DjangoTestSuiteRunner
from mule.base import Mule

from optparse import make_option

def make_test_runner(parent):
    class DistributedDjangoTestSuiteRunner(parent):
        options = (
            make_option('--auto-bootstrap', dest='auto_bootstrap', action='store_true',
                        help='Bootstrap a new database automatically.'),
            make_option('--id', dest='build_id', help='Identifies this build within a distributed model.',
                        default='default'),
            make_option('--db-prefix', type='string', dest='db_prefix', default='test',
                        help='Prefix to use for test databases. Default is ``test``.'),
            make_option('--distribute', dest='distribute', action='store_true',
                        help='Fire test jobs off to Celery queue and collect results.'),
        ) + getattr(parent, 'options', ())

        def __init__(self, auto_bootstrap=False, build_id='default', db_prefix='test', distribute=False, *args, **kwargs):
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
            
            self.distribute = distribute

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

        def setup_databases(self, *args, **kwargs):
            # We only need to setup databases if we need to bootstrap
            if self.auto_bootstrap:
                bootstrap = False
                for k, v in settings.DATABASES.iteritems():
                    if v.get('TEST_MIRROR'):
                        continue

                    if bootstrap:
                        continue
                
                    connection = connections[k]
                    qn = connection.ops.quote_name
                    test_database_name = connection.settings_dict['TEST_NAME']
                    cursor = connection.cursor()
                    suffix = connection.creation.sql_table_creation_suffix()
                    connection.creation.set_autocommit()

                    # HACK: this isnt an accurate check
                    try:
                        cursor.execute("CREATE DATABASE %s %s" % (qn(test_database_name), suffix))
                    except Exception, e:
                        print e
                        pass
                    else:
                        bootstrap = True
                    finally:
                        cursor.close()
                if not bootstrap:
                    return

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
            mule = Mule()
            result = mule.process(test_labels, runner='python manage.py mtest')
            return '\n'.join(result)
        
        def run_tests(self, test_labels, extra_tests=None, **kwargs):
            if self.distribute:
                return self.run_distributed_tests(test_labels, extra_tests=None, **kwargs)
            
            self.setup_test_environment()
            suite = self.build_suite(test_labels, extra_tests)

            old_config = self.setup_databases()

            result = self.run_suite(suite)

            self.teardown_databases(old_config)
            self.teardown_test_environment()

            return self.suite_result(suite, result)
    return DistributedDjangoTestSuiteRunner
DjangoTestSuiteRunner = make_test_runner(DjangoTestSuiteRunner)