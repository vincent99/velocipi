import time


def log(source, msg):
    t = time.localtime()
    print('[{:02d}:{:02d}:{:02d}] [{}] {}'.format(t[3], t[4], t[5], source, msg))
