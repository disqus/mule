from mule import conf

import warnings

def configure(**kwargs):
    for k, v in kwargs.iteritems():
        if not hasattr(conf, k):
            warnings.warn('Setting %k which is not defined by Mule' % k)
        setattr(conf, k, v)