import json
import logging

logger = logging.getLogger(__name__)


def load_config(path):
    logger.info(f"Loading config {path=}")

    with open(path) as f:
        return json.load(f)
