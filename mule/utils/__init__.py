import os
import fcntl

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

locks = {}

def acquire_lock(lock):
    fd = open(lock, 'w')
    fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB) # NB = non-blocking (raise IOError instead)
    fd.write(str(os.getpid()))
    locks[lock] = fd

def release_lock(lock):
    fd = locks.pop(lock)
    if not fd:
        return
    fcntl.lockf(fd, fcntl.LOCK_UN)
    fd.close()
    os.remove(lock)
    fd = None