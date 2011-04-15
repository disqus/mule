from collections import defaultdict
from Queue import Queue
from threading import Thread

import time

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
            except (KeyboardInterrupt, SystemExit):
                return
            except Exception, e:
                _results[ident].append({
                    'func': func,
                    'args': args,
                    'kwargs': kwargs,
                    'result': e,
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
            while self.workers and not self.tasks.empty():
                # Ensure we clean out dead workers
                for worker in list(self.workers):
                    if not worker.is_alive:
                        self.workers.pop(self.workers.index(worker))
                
                time.sleep(0.5)
        except KeyboardInterrupt:
            print '\n! Received keyboard interrupt, closing workers.\n'
        finally:
            del _results[id(self)]

        return _results[id(self)]