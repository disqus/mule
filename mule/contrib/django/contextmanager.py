from django.conf import settings
from django.core.management import call_command
from django.db import connections, router
from django.db.backends import DatabaseProxy
from django.db.models import get_apps, get_models, signals

from mule.contextmanager import BaseTestContextManager
from mule.contrib.django.loader import get_test_module
from mule.utils import import_string
from mule.utils.locking import get_setting_lock, release_setting_lock

class EnvContextManager(BaseTestContextManager):
    def __enter__(self):
        self.suite.setup_test_environment()
    
    def __exit__(self, type, value, traceback):
        self.suite.teardown_test_environment()

class DatabaseContextManager(BaseTestContextManager):
    def __enter__(self):
        suite = self.suite

        self.db_num = get_setting_lock('db', self.build_id)

        db_prefix = '%s_%s_%s_' % (suite.db_prefix, self.build_id, self.db_num)

        for k, v in settings.DATABASES.iteritems():
            # If TEST_NAME wasnt set, or we've set a non-default prefix
            if not v.get('TEST_NAME') or self.auto_bootstrap:
                settings.DATABASES[k]['TEST_NAME'] = db_prefix + settings.DATABASES[k]['NAME']

        suite.db_prefix = db_prefix
        
        # We only need to setup databases if we need to bootstrap
        if suite.auto_bootstrap:
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

        # Ensure we import all tests that could possibly be executed so that tables get created
        # and all signals get registered
        for app in get_apps():
            get_test_module(app)

            # Import the 'management' module within each installed app, to register
            # dispatcher events.
            try:
                import_string('%s.management' % app.__name__.rsplit('.', 1)[0])
            except (ImportError, AttributeError):
                pass

        # HACK: We need to kill post_syncdb receivers to stop them from sending when the databases
        #       arent fully ready.
        post_syncdb_receivers = signals.post_syncdb.receivers
        signals.post_syncdb.receivers = []

        if not bootstrap:
            old_names = []
            mirrors = []
            for alias in connections:
                connection = connections[alias]

                if connection.settings_dict['TEST_MIRROR']:
                    mirrors.append((alias, connection))
                    mirror_alias = connection.settings_dict['TEST_MIRROR']
                    connections._connections[alias] = DatabaseProxy(connections[mirror_alias], alias)
                else:
                    old_names.append((connection, connection.settings_dict['NAME']))

                    # Ensure NAME is now set to TEST_NAME
                    connection.settings_dict['NAME'] = settings.DATABASES[alias]['TEST_NAME']

                    can_rollback = connection.creation._rollback_works()
                    # Ensure we setup ``SUPPORTS_TRANSACTIONS``
                    connection.settings_dict['SUPPORTS_TRANSACTIONS'] = can_rollback

                    # Get a cursor (even though we don't need one yet). This has
                    # the side effect of initializing the test database.
                    cursor = connection.cursor()

                    # Ensure our database is clean
                    call_command('flush', verbosity=0, interactive=False, database=alias)

                # XXX: do we need to flush the cache db?

                # if settings.CACHE_BACKEND.startswith('db://'):
                #     from django.core.cache import parse_backend_uri
                #     _, cache_name, _ = parse_backend_uri(settings.CACHE_BACKEND)
                #     call_command('createcachetable', cache_name)
        else:
            old_names, mirrors = suite.setup_databases()

        signals.post_syncdb.receivers = post_syncdb_receivers

        # XXX: we could truncate all tables in the teardown phase and
        #      run the syncdb steps on each iteration (to ensure compatibility w/ transactions)
        for app in get_apps():
            app_models = list(get_models(app, include_auto_created=True))
            for db in connections:
                connection = connections[alias]
                
                # Get a cursor (even though we don't need one yet). This has
                # the side effect of initializing the test database.
                cursor = connection.cursor()
                
                all_models = [m for m in app_models if router.allow_syncdb(db, m)]
                if not all_models:
                    continue
                signals.post_syncdb.send(app=app, created_models=all_models, verbosity=suite.verbosity,
                                         db=db, sender=app, interactive=False)

        self.old_config = old_names, mirrors

    def __exit__(self, type, value, traceback):
        suite = self.suite
        
        # If we were bootstrapping we dont tear down databases
        if suite.auto_bootstrap:
            return

        suite.teardown_databases(self.old_config)
        
        release_setting_lock('db', self.build_id, self.db_num)