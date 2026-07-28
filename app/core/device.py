"""Device auto-selection for local models (MPS / CUDA / CPU).

Torch is imported lazily so the API process, which never runs models,
does not pay the torch import cost. Only worker-side services that
actually load models should call get_device().
"""

import os
import platform
from functools import lru_cache

os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")


@lru_cache
def get_device() -> str:
    """Return 'mps' | 'cuda' | 'cpu', preferring Apple Silicon MPS."""
    from app.core.config import get_settings

    if get_settings().force_cpu or os.getenv("FORCE_CPU", "").lower() in ("1", "true", "yes"):
        return "cpu"

    import torch

    if torch.backends.mps.is_available():
        try:
            # Verify MPS actually works with a test tensor
            test_tensor = torch.zeros(1, device="mps")
            del test_tensor
            torch.mps.empty_cache()
            return "mps"
        except Exception:
            pass

    if torch.cuda.is_available():
        return "cuda"

    return "cpu"


def log_device_info() -> None:
    import torch

    from app.core.logging import get_logger

    log = get_logger(__name__)
    device = get_device()
    log.info(
        "local_model_device",
        device=device,
        torch_version=torch.__version__,
        platform=platform.machine(),
    )
