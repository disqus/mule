from collections import defaultdict
from Queue import Queue
from threading import Thread

import traceback

_results = defaultdict(list)

class Worker(Thread):
    """Thread executing tasks from a given tasks queue"""
    def __init__(self, tasks):
        Thread.__init__(self)
        self.tasks = tasks
        self.daemon = True
        self.start()
    
    def run(self):
        interrupt = False
        while True:
            func, args, kwargs, ident = self.tasks.get()

            if interrupt:
                self.tasks.task_done()
                continue
            
            try:
                _results[ident].append({
                    'func': func,
                    'args': args,
                    'kwargs': kwargs,
                    'result': func(*args, **kwargs),
                })
            except KeyboardInterrupt, e:
                # We don't record results if we hit an interrupt
                interrupt = True
            except Exception, e:
                _results[ident].append({
                    'func': func,
                    'args': args,
                    'kwargs': kwargs,
                    'result': traceback.format_exc(),
                })
            finally:
                self.tasks.task_done()

class ThreadPool:
    """Pool of threads consuming tasks from a queue"""
    def __init__(self, num_threads):
        self.tasks = Queue()
        self.workers = []
        for _ in xrange(num_threads):
            self.workers.append(Worker(self.tasks))
    
    def add(self, func, *args, **kwargs):
        """Add a task to the queue"""
        self.tasks.put((func, args, kwargs, id(self)), False)

    def join(self):
        """Wait for completion of all the tasks in the queue"""
        try:
            self.tasks.join()
            return _results[id(self)]
        except KeyboardInterrupt:
            print '\nReceived keyboard interrupt, closing workers.\n'
            return _results[id(self)]
        finally:
            del _results[id(self)]