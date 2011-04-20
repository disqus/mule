import fcntl
import os

LOCK_DIR = '/var/tmp'

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
    
def get_setting_lock(setting, build_id, max_locks=None):
    # XXX: Pretty sure this needs try/except to stop race condition
    num = 0
    while not max_locks or num < max_locks:
        lock_file = lock_for_setting(setting, build_id, num)
        try:
            acquire_lock(lock_file)
        except IOError:
            # lock unavailable
            num += 1
        else:
            break
    if num == max_locks:
        raise OSError
    return num

def release_setting_lock(setting, build_id, num):
    lock_file = lock_for_setting(setting, build_id, num)
    release_lock(lock_file)

def lock_for_setting(setting, build_id, num=0):
    return os.path.join(LOCK_DIR, 'mule:%s_%s_%s' % (setting, build_id, num))