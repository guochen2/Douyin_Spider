import builtins
import sys


class QueueLogWriter:
    """将 stdout/stderr 写入队列，供 GUI 线程安全地显示。"""

    def __init__(self, log_queue, stream_name='stdout', original=None):
        self.log_queue = log_queue
        self.stream_name = stream_name
        self.original = original
        self._buffer = ''

    def write(self, text):
        if not text:
            return
        self._buffer += text
        while '\n' in self._buffer:
            line, self._buffer = self._buffer.split('\n', 1)
            self.log_queue.put((self.stream_name, line + '\n'))
        if self.original is not None:
            try:
                self.original.write(text)
            except Exception:
                pass

    def flush(self):
        if self._buffer:
            self.log_queue.put((self.stream_name, self._buffer))
            self._buffer = ''
        if self.original is not None:
            try:
                self.original.flush()
            except Exception:
                pass

    def isatty(self):
        return False


def install_queue_logging(log_queue):
    stdout = QueueLogWriter(log_queue, 'stdout', sys.stdout)
    stderr = QueueLogWriter(log_queue, 'stderr', sys.stderr)
    sys.stdout = stdout
    sys.stderr = stderr

    original_print = builtins.print

    def gui_print(*args, **kwargs):
        file = kwargs.get('file', sys.stdout)
        if file in (sys.stdout, sys.stderr):
            sep = kwargs.get('sep', ' ')
            end = kwargs.get('end', '\n')
            text = sep.join(str(a) for a in args) + end
            stream_name = 'stderr' if file is sys.stderr else 'stdout'
            log_queue.put((stream_name, text))
            return
        original_print(*args, **kwargs)

    builtins.print = gui_print
    return stdout, stderr
