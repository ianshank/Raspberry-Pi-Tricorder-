"""HailoRT inference adapter for Hailo-8L accelerator on Raspberry Pi 5."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import numpy as np

logger = logging.getLogger(__name__)


class HailoAdapter:
    """Inference adapter backed by HailoRT.

    Implements the :class:`InferenceAdapter` protocol so it can be used
    with any :class:`BaseModel` subclass.  When the ``hailo_platform``
    package is not installed the adapter degrades gracefully: ``load()``
    returns ``False`` and ``predict()`` returns a zero array matching the
    input shape.
    """

    def __init__(
        self,
        device_id: int = 0,
        hef_path: Optional[str] = None,
    ) -> None:
        self._device_id = device_id
        self._hef_path = hef_path
        self._loaded = False
        self._vdevice = None
        self._network_group = None
        self._input_vstreams = None
        self._output_vstreams = None
        logger.info(
            "HailoAdapter created (device_id=%d, hef_path=%s)",
            device_id,
            hef_path,
        )

    # ------------------------------------------------------------------
    # InferenceAdapter protocol
    # ------------------------------------------------------------------

    def load(self, model_path: str) -> bool:
        """Load a compiled HEF model onto the Hailo device.

        Parameters
        ----------
        model_path:
            Filesystem path to a ``.hef`` file.  If *hef_path* was
            supplied at construction time, *model_path* is ignored and
            the constructor value is used instead.

        Returns
        -------
        bool
            ``True`` when the model is ready for inference, ``False``
            when loading fails (e.g. missing runtime library).
        """
        effective_path = self._hef_path or model_path
        try:
            from hailo_platform import HEF, VDevice, ConfigureParams  # type: ignore[import-untyped]
        except ImportError:
            logger.warning(
                "hailo_platform is not installed; "
                "HailoAdapter will operate in stub mode"
            )
            return False

        try:
            hef = HEF(effective_path)
            self._vdevice = VDevice(device_ids=[self._device_id])
            configure_params = ConfigureParams.create_from_hef(
                hef=hef, interface=self._vdevice,
            )
            self._network_group = self._vdevice.configure(  # type: ignore[attr-defined]
                hef, configure_params
            )
            self._loaded = True
            logger.info(
                "Hailo model loaded from %s on device %d",
                effective_path,
                self._device_id,
            )
            return True
        except Exception:
            logger.error(
                "Failed to load HEF from %s on device %d",
                effective_path,
                self._device_id,
                exc_info=True,
            )
            self._loaded = False
            return False

    def predict(self, input_data: np.ndarray) -> np.ndarray:
        """Run inference on *input_data*.

        When the model has not been loaded successfully the method
        returns an array of zeros with the same shape as the input.
        """
        if not self._loaded:
            logger.warning(
                "predict() called on unloaded HailoAdapter; "
                "returning zeros"
            )
            return np.zeros_like(input_data)

        try:
            result = self._network_group.run(input_data)  # type: ignore[attr-defined]
            return np.asarray(result)
        except Exception:
            logger.error(
                "Hailo inference failed on device %d",
                self._device_id,
                exc_info=True,
            )
            return np.zeros_like(input_data)

    def get_info(self) -> Dict[str, Any]:
        """Return metadata about this adapter."""
        return {
            "backend": "hailort",
            "device_id": self._device_id,
            "hef_path": self._hef_path,
            "loaded": self._loaded,
        }
