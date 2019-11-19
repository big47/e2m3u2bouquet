# logging
#
# One can simply use
# import log
# print>>log, "Some text"
# because the log unit looks enough like a file!

import sys
from cStringIO import StringIO
import threading

logfile = StringIO()
# Need to make our operations thread-safe.
_lock = threading.Lock()

def write(data):
    with _lock:
       if logfile.tell() > 2000:
           # Do a sort of 2k round robin
           logfile.reset()
       logfile.write(data)
    sys.stdout.write(data)

def getvalue():
    with _lock:
       pos = logfile.tell()
       head = logfile.read()
       logfile.reset()
       tail = logfile.read(pos)
    return head + tail
