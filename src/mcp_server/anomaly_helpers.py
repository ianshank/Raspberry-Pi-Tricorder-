"""Pure helper functions for anomaly detection pipeline.

Extracted from server.py for testability and separation of concerns.
All functions are stateless and have no server dependencies.
"""

import hashlib
import math
from typing import Any, Dict, Optional

from utils.constants import DEFAULT_SEVERITY_THRESHOLDS


def coerce_float(value: Any) -> Optional[float]:
    """Attempt to coerce *value* to a finite float, returning None on failure."""
    try:
        candidate = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(candidate):
        return None
    return candidate


def coerce_bool(value: Any) -> Optional[bool]:
    """Attempt to coerce *value* to a bool, returning None on failure."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y", "on"}:
            return True
        if lowered in {"false", "0", "no", "n", "off"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return None


def severity_from_score(
    score: Optional[float],
    thresholds: Optional[Dict[str, float]] = None,
) -> str:
    """Map an anomaly score to a severity label.

    Args:
        score: Anomaly score in [0, 1], or None.
        thresholds: Dict with keys ``critical``, ``high``, ``medium``.
            Defaults to :data:`DEFAULT_SEVERITY_THRESHOLDS`.
    """
    if score is None:
        return "UNKNOWN"
    t = thresholds if isinstance(thresholds, dict) else DEFAULT_SEVERITY_THRESHOLDS
    if score >= t.get("critical", 0.9):
        return "CRITICAL"
    if score >= t.get("high", 0.75):
        return "HIGH"
    if score >= t.get("medium", 0.5):
        return "MEDIUM"
    return "LOW"


def extract_anomaly_summary(
    scan_result: Any,
    latest_history_entry: Optional[Dict[str, Any]],
    fallback_threshold: float,
    severity_thresholds: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Build a normalised anomaly summary from heterogeneous scan/history data."""
    scan_payload = scan_result if isinstance(scan_result, dict) else {}
    model_output = scan_payload.get("output", {})
    output_payload = model_output if isinstance(model_output, dict) else {}
    history_payload = latest_history_entry if isinstance(latest_history_entry, dict) else {}

    anomaly_score = coerce_float(output_payload.get("anomaly_score"))
    if anomaly_score is None:
        anomaly_score = coerce_float(scan_payload.get("anomaly_score"))
    if anomaly_score is None:
        anomaly_score = coerce_float(history_payload.get("anomaly_score"))

    is_anomaly = coerce_bool(output_payload.get("is_anomaly"))
    if is_anomaly is None:
        is_anomaly = coerce_bool(scan_payload.get("is_anomaly"))
    if is_anomaly is None and anomaly_score is not None:
        is_anomaly = anomaly_score >= fallback_threshold
    if is_anomaly is None:
        is_anomaly = False

    confidence = coerce_float(scan_payload.get("confidence"))
    if confidence is None:
        confidence = coerce_float(output_payload.get("confidence"))
    if confidence is None:
        confidence = coerce_float(history_payload.get("confidence"))

    return {
        "anomaly_score": anomaly_score,
        "is_anomaly": bool(is_anomaly),
        "severity": severity_from_score(anomaly_score, severity_thresholds),
        "confidence": confidence,
    }


def build_anomaly_id(
    model_id: str,
    scan_result: Any,
    latest_history_entry: Optional[Dict[str, Any]],
    summary: Dict[str, Any],
) -> str:
    """Build a stable ID for anomaly events so acknowledgments can be tracked."""
    reference_timestamp = ""
    if isinstance(latest_history_entry, dict):
        raw_ts = latest_history_entry.get("timestamp")
        if raw_ts is not None:
            reference_timestamp = str(raw_ts)

    if not reference_timestamp and isinstance(scan_result, dict):
        raw_scan_ts = scan_result.get("timestamp")
        if raw_scan_ts is not None:
            reference_timestamp = str(raw_scan_ts)
        else:
            raw_output = scan_result.get("output")
            if isinstance(raw_output, dict):
                raw_output_ts = raw_output.get("timestamp")
                if raw_output_ts is not None:
                    reference_timestamp = str(raw_output_ts)

    anomaly_score = coerce_float(summary.get("anomaly_score"))
    score_label = "na" if anomaly_score is None else f"{anomaly_score:.4f}"
    severity = str(summary.get("severity", "UNKNOWN"))
    timestamp_label = reference_timestamp or "live"

    seed = f"{model_id}|{severity}|{score_label}|{timestamp_label}"
    digest = hashlib.sha1(seed.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]
    return f"anom-{digest}"
