"""Native editor entry point. BSB, MPI and simulators are not runtime dependencies."""
from __future__ import annotations
import argparse
import json
import logging
import os
from pathlib import Path
import sys
import threading
import traceback
import webbrowser


def configure(data_dir=None):
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    assets = base / 'DeformationAlgorithm'
    resources = base / 'resources'
    default = Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local/share')) / 'CerebellumDesigner'
    data = Path(data_dir or default).expanduser().resolve()
    data.mkdir(parents=True, exist_ok=True)
    os.environ['DF_PROJECT_ROOT'] = str(data)
    os.environ['DF_MODEL_REPO'] = str(resources / 'src/cerebellar-models')
    os.environ['CD_APP_ASSETS'] = str(assets)
    os.environ['CD_RESOURCE_ROOT'] = str(resources)
    os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
    os.environ.setdefault('OMP_NUM_THREADS', '1')
    if not getattr(sys, 'frozen', False):
        sys.path.insert(0, str(assets))
    return data


def main():
    parser = argparse.ArgumentParser(description='Cerebellum Designer native configuration editor')
    parser.add_argument('--data-dir')
    parser.add_argument('--port', type=int, default=8891)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    data = configure(args.data_dir)
    log = data / 'desktop.log'
    logging.basicConfig(filename=log, level=logging.INFO, encoding='utf-8',
                        format='%(asctime)s %(levelname)s %(message)s')
    try:
        if args.self_test:
            from native_checks import self_test
            result = self_test(data)
            (data / 'self-test.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
            return 0
        from cereb_remorph.designer import Handler
        from http.server import ThreadingHTTPServer
        class DesktopHandler(Handler):
            def log_message(self, fmt, *values):
                logging.info(fmt, *values)
        server = None
        # Never take over another Designer process or change its configuration.
        for port in ([0] if args.port == 0 else range(args.port, args.port + 20)):
            try:
                server = ThreadingHTTPServer(('127.0.0.1', port), DesktopHandler)
                break
            except OSError:
                continue
        if server is None:
            raise RuntimeError('No free local port. Close another Designer instance and try again.')
        server.daemon_threads = True
        url = f'http://127.0.0.1:{server.server_port}/'
        info = {'url':url, 'pid':os.getpid(), 'data_directory':str(data)}
        state = data / f'server-{os.getpid()}.json'
        state.write_text(json.dumps(info, indent=2), encoding='utf-8')
        logging.info('Native editor ready: %s', url)
        if not args.no_browser:
            threading.Timer(0.5, lambda: webbrowser.open(url)).start()
        try:
            server.serve_forever(poll_interval=0.2)
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
            state.unlink(missing_ok=True)
        return 0
    except Exception:
        logging.exception('Native editor failed')
        (data / 'last-error.txt').write_text(traceback.format_exc(), encoding='utf-8')
        if sys.platform == 'win32' and not args.self_test and not args.no_browser:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, f'Unable to start Cerebellum Designer.\nDetails: {data / "last-error.txt"}', 'Cerebellum Designer', 0x10)
        if sys.stderr:
            traceback.print_exc()
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
