"""JSON state with optional persistent storage; legacy paths remain the default."""

import json
import os
import tempfile
import threading
from pathlib import Path

state_lock = threading.RLock()


def data_path(filename):
    directory = os.getenv('DATA_DIR')
    path = Path(filename)
    if directory and not path.is_absolute():
        path = Path(directory).expanduser() / path
    return path


def read_json(filename, default=None):
    with state_lock:
        path = data_path(filename)
        if not path.exists():
            return {} if default is None else default
        with path.open(encoding='utf-8') as stream:
            data = json.load(stream)
        if not isinstance(data, dict):
            raise ValueError(f'{path.name}: expected a JSON object')
        return data


def write_json(filename, data):
    """Return only after the complete file is written; propagate write failures."""
    with state_lock:
        path = data_path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode='w', encoding='utf-8', dir=path.parent,
                prefix=path.name + '.', suffix='.tmp', delete=False,
            ) as stream:
                temporary = stream.name
                json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)


def migrate_to_data_dir(filenames):
    """Copy existing state once when DATA_DIR is enabled. Never overwrite it."""
    if not os.getenv('DATA_DIR'):
        return
    with state_lock:
        for filename in filenames:
            source = Path(filename)
            target = data_path(filename)
            if target.exists() or not source.exists() or source.resolve() == target.resolve():
                continue
            with source.open(encoding='utf-8') as stream:
                data = json.load(stream)
            if not isinstance(data, dict):
                raise ValueError(f'{source.name}: expected a JSON object')
            write_json(filename, data)
