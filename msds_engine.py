"""설정값에 따라 V6 안정판 또는 V7을 선택하는 호환 진입점."""

from __future__ import annotations

import json
import os


def load_engine_version(config_path=None):
    path = config_path or os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            value = str(json.load(handle).get("msds_engine_version", "v6")).strip().casefold()
    except (OSError, ValueError, TypeError):
        value = "v6"
    return value if value in {"v6", "v7"} else "v6"


SELECTED_ENGINE_VERSION = load_engine_version()
if SELECTED_ENGINE_VERSION == "v7":
    from msds_engine_v7 import (  # noqa: F401
        MES_MASTER_LOAD_ERROR,
        MES_MASTER_MAP,
        MSDSEngineV7 as SelectedMSDSEngine,
        VERSION,
        analyze_msds,
        process_pdf,
    )
else:
    from msds_engine_v6 import (  # noqa: F401
        MES_MASTER_LOAD_ERROR,
        MES_MASTER_MAP,
        MSDSEngineV6 as SelectedMSDSEngine,
        VERSION,
        analyze_msds,
        process_pdf,
    )
