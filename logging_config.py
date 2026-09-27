import logging
import os
import sys
from logging.handlers import RotatingFileHandler


def setup_logging():
    log_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(log_dir, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    root = logging.getLogger()
    if root.handlers:  # avoid duplicate handlers on reload
        return
    root.setLevel(logging.INFO)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    root.addHandler(console)

    try:
        file_handler = RotatingFileHandler(
            os.path.join(log_dir, "app.log"), maxBytes=2_000_000, backupCount=3
        )
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
    except Exception:
        # If the filesystem is read-only (some hosts), console logging still works.
        pass
