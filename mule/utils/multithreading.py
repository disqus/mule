from collections import defaultdict
from Queue import Queue
from threading import Thread
import thread

_results = defaultdict(list)

class Worker(Thread):
    """Thread executing tasks from a given tasks queue"""
    def __init__(self, tasks):
        Thread.__init__(self)
        self.tasks = tasks
        self.daemon = True
        self.start()
    
    def run(self):
        while True:
            func, args, kwargs, ident = self.tasks.get()
            try:
                _results[ident].append({
                    'func': func,
                    'args': args,
                    'kwargs': kwargs,
                    'result': func(*args, **kwargs),
                })
            finally:
                self.tasks.task_done()

class ThreadPool:
    """Pool of threads consuming tasks from a queue"""
    def __init__(self, num_threads):
        self.tasks = Queue(num_threads)
        for _ in xrange(num_threads):
            Worker(self.tasks)
    
    def add(self, func, *args, **kwargs):
        """Add a task to the queue"""
        self.tasks.put((func, args, kwargs, id(self)))

    def join(self):
        """Wait for completion of all the tasks in the queue"""
        self.tasks.join()
        return _results[id(self)]