context_managers = set()

def register_context_manager(cls):
    context_managers.add(cls)

def get_context_managers():
    return context_managers

class BaseTestContextManager(object):
    def __init__(self, build_id):
        self.build_id = build_id

    def __enter__(self):
        pass

    def __exit__(self):
        pass