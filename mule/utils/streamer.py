from cStringIO import StringIO

class Streamer(object):
    def __init__(self, fp, *args, **kwargs):
        self.fp = fp
        self.stringio = StringIO()
    
    def write(self, *args, **kwargs):
        self.fp.write(*args, **kwargs)
        self.stringio.write(*args, **kwargs)
    
    def getvalue(self, *args, **kwargs):
        return self.stringio.getvalue(*args, **kwargs)
    
    def read(self, *args, **kwargs):
        return self.stringio.read(*args, **kwargs)

    def flush(self):
        return self.stringio.flush()