#!/usr/bin/env python

try:
    from setuptools import setup, find_packages
except ImportError:
    from ez_setup import use_setuptools
    use_setuptools()
    from setuptools import setup, find_packages

import os.path

tests_require = [
    'redis',
    'unittest2',
    'dingus',
]
setup(
    name='Mule',
    version='0.1.6',
    author='DISQUS',
    author_email='opensource@disqus.com',
    url='http://github.com/disqus/mule',
    description = 'Distributed Testing',
    packages=find_packages(),
    zip_safe=False,
    install_requires=[
        'celery',
        'uuid',
        'kombu',
    ],
    dependency_links=[
        'https://github.com/disqus/kombu/tarball/master#egg=kombu',
    ],
    tests_require=tests_require,
    extras_require={'test': tests_require},
    test_suite='mule.runtests.runtests',
    include_package_data=True,
    entry_points = {
        'console_scripts': [
            'mule = mule.scripts.runner:main',
        ],
    },
    classifiers=[
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'Operating System :: OS Independent',
        'Topic :: Software Development'
    ],
)
