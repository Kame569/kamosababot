import logging
from pathlib import Path

def setup_logging():
    Path("data/logs").mkdir(parents=True, exist_ok=True)

    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(level=logging.INFO, format=fmt)

    # 追加でファイルにも落としたい場合はここでHandler追加してOK
    return logging.getLogger("App")
