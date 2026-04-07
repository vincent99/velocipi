import time


def log(source, msg):
    t = time.localtime()
    print('[{:04d}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}Z] [{}] {}'.format(
        t[0], t[1], t[2], t[3], t[4], t[5], source, msg))
