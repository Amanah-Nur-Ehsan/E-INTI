"""Device auto-selection and CPU budgeting for local models.

Torch is imported lazily so the API process, which never runs models,
does not pay the torch import cost. Only worker-side services that
actually load models should call get_device().

Two mechanisms bound how much CPU local inference can take, which is what
lets several analyses run concurrently on a shared box:

* `torch_num_threads` caps torch's *intra*-op parallelism. Left alone,
  torch grabs every core for a single matmul.
* `local_inference()` is a process-wide semaphore around the actual
  forward passes, so two concurrent analyses never both run torch. Peak
  CPU therefore stays near `torch_num_threads` cores no matter how many
  analyses are in flight, while their LLM/network waits still overlap
  freely.
"""

import os
import platform
import threading
from contextlib import contextmanager
from functools import lru_cache

os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

#: OpenMP/MKL read these when their runtime initializes, which happens on
#: `import torch` -- too early for a settings lookup, and too early for
#: torch.set_num_threads() to have run. Seeding them at module import (this
#: module is imported well before any lazy `import torch`) is the only way
#: to catch that path; docker-compose sets them explicitly too. The
#: authoritative cap is still torch.set_num_threads() in get_device().
_THREAD_DEFAULT = os.getenv("TORCH_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", _THREAD_DEFAULT)
os.environ.setdefault("MKL_NUM_THREADS", _THREAD_DEFAULT)

#: Only one local-model forward pass at a time, process-wide. Sized 1
#: deliberately: this is the dial that keeps peak CPU near one core.
_INFERENCE_SEMAPHORE = threading.Semaphore(1)


@contextmanager
def local_inference():
    """Serialize local-model forward passes across threads.

    Acquire around a *batch*, never around a whole multi-batch call --
    holding it for an entire draft's embeddings would starve any other
    analysis running in the same worker for the full duration.
    """
    with _INFERENCE_SEMAPHORE:
        yield


@lru_cache
def get_device() -> str:
    """Return 'mps' | 'cuda' | 'cpu', preferring Apple Silicon MPS.

    Also applies the torch thread cap, since this is the one function every
    model-loading path already calls before touching torch.
    """
    from app.core.config import get_settings

    settings = get_settings()
    forced_cpu = settings.force_cpu or os.getenv("FORCE_CPU", "").lower() in ("1", "true", "yes")

    import torch

    # Cap before any model runs. Applied on every path including force_cpu,
    # because "CPU only" is exactly when unbounded threads hurt most.
    torch.set_num_threads(max(1, settings.torch_num_threads))

    if forced_cpu:
        return "cpu"

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
