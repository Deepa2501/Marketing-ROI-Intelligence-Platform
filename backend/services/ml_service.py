"""
ML service layer for ROI prediction.

Loads the trained early-stage Random Forest pipeline (preprocessing +
model, saved as a single joblib artifact) once per process and reuses
it for every request. Never retrains on request. Metadata (metrics,
comparison figures, feature list) is read from the JSON file produced
by python/train_roi_model.py — nothing here is hardcoded.
"""

import json
import os
import threading
from typing import Optional

import joblib
import pandas as pd

_model_lock = threading.Lock()
_model_cache: dict = {"pipeline": None, "loaded": False, "error": None}

_metadata_lock = threading.Lock()
_metadata_cache: dict = {"data": None, "loaded": False, "error": None}

CATEGORICAL_FEATURES = [
    "Campaign_Type",
    "Target_Audience",
    "Channel_Used",
    "Language",
    "Customer_Segment",
]
NUMERIC_FEATURES = ["Duration", "Acquisition_Cost"]
REQUIRED_FIELDS = CATEGORICAL_FEATURES + NUMERIC_FEATURES


class ModelUnavailableError(Exception):
    """Raised when the trained model artifact hasn't been produced yet
    (i.e. python/train_roi_model.py hasn't been run against the real
    dataset). Routes catch this and return a clear, non-crashing error.
    """


def get_pipeline(model_path: str):
    with _model_lock:
        if _model_cache["loaded"]:
            if _model_cache["pipeline"] is None:
                raise ModelUnavailableError(_model_cache["error"])
            return _model_cache["pipeline"]

        if not os.path.exists(model_path):
            _model_cache["loaded"] = True
            _model_cache["pipeline"] = None
            _model_cache["error"] = (
                f"Model artifact not found at {model_path}. Run python/train_roi_model.py first."
            )
            raise ModelUnavailableError(_model_cache["error"])

        try:
            pipeline = joblib.load(model_path)
            _model_cache["pipeline"] = pipeline
            _model_cache["loaded"] = True
            _model_cache["error"] = None
            return pipeline
        except Exception as exc:  # noqa: BLE001
            _model_cache["loaded"] = True
            _model_cache["pipeline"] = None
            _model_cache["error"] = f"Failed to load model artifact: {exc.__class__.__name__}"
            raise ModelUnavailableError(_model_cache["error"]) from exc


def get_metadata(metadata_path: str) -> dict:
    with _metadata_lock:
        if _metadata_cache["loaded"]:
            if _metadata_cache["data"] is None:
                raise ModelUnavailableError(_metadata_cache["error"])
            return _metadata_cache["data"]

        if not os.path.exists(metadata_path):
            _metadata_cache["loaded"] = True
            _metadata_cache["data"] = None
            _metadata_cache["error"] = (
                f"Model metadata not found at {metadata_path}. Run python/train_roi_model.py first."
            )
            raise ModelUnavailableError(_metadata_cache["error"])

        try:
            with open(metadata_path) as f:
                data = json.load(f)
            _metadata_cache["data"] = data
            _metadata_cache["loaded"] = True
            _metadata_cache["error"] = None
            return data
        except Exception as exc:  # noqa: BLE001
            _metadata_cache["loaded"] = True
            _metadata_cache["data"] = None
            _metadata_cache["error"] = f"Failed to read model metadata: {exc.__class__.__name__}"
            raise ModelUnavailableError(_metadata_cache["error"]) from exc


def reset_cache() -> None:
    """Utility for tests."""
    with _model_lock:
        _model_cache["pipeline"] = None
        _model_cache["loaded"] = False
        _model_cache["error"] = None
    with _metadata_lock:
        _metadata_cache["data"] = None
        _metadata_cache["loaded"] = False
        _metadata_cache["error"] = None


def validate_prediction_input(payload: Optional[dict]) -> list:
    """Return a list of human-readable error strings. Empty list means valid."""
    errors = []

    if not isinstance(payload, dict):
        return ["Request body must be a JSON object."]

    for field in REQUIRED_FIELDS:
        if field not in payload or payload[field] in (None, ""):
            errors.append(f"'{field}' is required.")

    if errors:
        # Don't attempt numeric/categorical checks on fields that are missing.
        return errors

    for field in CATEGORICAL_FEATURES:
        if not isinstance(payload[field], str) or not payload[field].strip():
            errors.append(f"'{field}' must be a non-empty string.")

    duration = payload.get("Duration")
    if not isinstance(duration, (int, float)) or isinstance(duration, bool):
        errors.append("'Duration' must be a number.")
    elif duration <= 0:
        errors.append("'Duration' must be a positive number.")
    elif duration > 365:
        errors.append("'Duration' must be 365 days or fewer.")

    cost = payload.get("Acquisition_Cost")
    if not isinstance(cost, (int, float)) or isinstance(cost, bool):
        errors.append("'Acquisition_Cost' must be a number.")
    elif cost < 0:
        errors.append("'Acquisition_Cost' must not be negative.")

    return errors


def predict_roi(model_path: str, payload: dict) -> float:
    pipeline = get_pipeline(model_path)
    row = {field: payload[field] for field in REQUIRED_FIELDS}
    X = pd.DataFrame([row])
    prediction = pipeline.predict(X)[0]
    return float(prediction)


def get_feature_importance(model_path: str) -> list:
    """Extract feature importances from the trained RandomForestRegressor
    inside the pipeline, mapped back to human-readable (expanded)
    one-hot column names. Computed from the artifact, not hardcoded.
    """
    pipeline = get_pipeline(model_path)

    preprocessor = pipeline.named_steps.get("preprocessor")
    model = pipeline.named_steps.get("model")

    if preprocessor is None or model is None or not hasattr(model, "feature_importances_"):
        raise ModelUnavailableError("Loaded model does not expose feature importances.")

    feature_names = list(preprocessor.get_feature_names_out())
    importances = model.feature_importances_

    paired = sorted(zip(feature_names, importances), key=lambda pair: pair[1], reverse=True)

    return [{"feature": name, "importance": round(float(value), 6)} for name, value in paired]
