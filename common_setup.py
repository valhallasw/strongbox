from ez_setup import use_setuptools
use_setuptools()
from setuptools import setup, find_packages
import copy, os

common = dict(
    author = "Sabren Enterprises, Inc.",
    author_email  = "help@webappworkshop.com",
    license = "LGPL",
)

def common_setup(name, **flags):
    etc = copy.deepcopy(common)

    etc['name'] = name
    etc['py_modules']=[name]
    etc['url'] = 'http://webappworkshop.com/pypi/%s' % name

    exec 'from %s import _eggData' % name
    etc.update(_eggData)
    
    etc.update(flags)
    setup(**etc)
