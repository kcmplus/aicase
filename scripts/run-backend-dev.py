"""Run the local API and its inventory worker together; stop both on exit."""
import subprocess
import os
import signal
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    children = []
    try:
        children.append(subprocess.Popen([sys.executable, '-u', 'backend/manage.py', 'runserver', '127.0.0.1:8000'], cwd=ROOT, start_new_session=os.name=='posix'))
        children.append(subprocess.Popen([sys.executable, '-u', 'backend/manage.py', 'sync_device_inventory', '--all', '--watch'], cwd=ROOT, start_new_session=os.name=='posix'))
        while all(child.poll() is None for child in children):
            time.sleep(0.5)
        return next(child.returncode for child in children if child.returncode is not None)
    except KeyboardInterrupt:
        return 0
    finally:
        for child in children:
            try:
                if os.name == 'posix':
                    os.killpg(child.pid, signal.SIGTERM)
                elif child.poll() is None:
                    child.terminate()
            except ProcessLookupError:
                pass
        for child in children:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == '__main__':
    def stop(_signum, _frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    sys.exit(main())
