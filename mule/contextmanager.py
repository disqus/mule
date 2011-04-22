# XXX: Must be an ordered list
context_managers = list()

def register_context_manager(cls):
    if cls not in context_managers:
        context_managers.append(cls)

def get_context_managers():
    return context_managers

class BaseTestContextManager(object):
    # XXX: All context managers MUST handle **kwargs in __init__
    def __init__(self, build_id, suite, **kwargs):
        self.suite = suite
        self.build_id = build_id

    def __enter__(self):
        pass

    def __exit__(self, type, value, traceback):
        pass