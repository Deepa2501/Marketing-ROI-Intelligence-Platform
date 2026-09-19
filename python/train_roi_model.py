"""
Train the early-stage ROI Random Forest model used by the Flask API.

Run from the repository root:

    python python/train_roi_model.py

What it does:
1. Loads data/cleaned/marketing_campaign_cleaned.csv
2. Trains the primary early-stage model (Random Forest, leakage-safe
   feature set: no Revenue/Impressions/Clicks/Leads/Conversions/Engagement_Score)
3. Also trains two reference models used by /api/model-comparison:
   - cost_only: Random Forest using Acquisition_Cost alone
   - strategy_only: Linear Regression using only campaign-strategy
     categoricals (no Acquisition_Cost)
4. Evaluates all three with a held-out test split (fixed random_state)
5. Saves the primary model (full sklearn Pipeline, including
   preprocessing) to models/roi_early_stage_model.joblib via joblib
6. Saves metadata + all three models' metrics to
   reports/roi_model_metadata.json

No metric in the output is hardcoded — everything is computed from
whatever CSV is found at DATA_PATH.
"""

import json
import os
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

RANDOM_STATE = 42

# n_estimators/max_depth chosen for a strong fit within reasonable training
# time; increase n_estimators (e.g. 300-500) and/or remove max_depth if
# training on more capable hardware and you want to push R² further.

CATEGORICAL_FEATURES = [
    "Campaign_Type",
    "Target_Audience",
    "Channel_Used",
    "Language",
    "Customer_Segment",
]
NUMERIC_FEATURES = ["Duration", "Acquisition_Cost"]
EARLY_STAGE_FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES
TARGET = "ROI"

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.environ.get("DATA_PATH", os.path.join(REPO_ROOT, "data", "cleaned", "marketing_campaign_cleaned.csv"))
MODEL_OUTPUT_PATH = os.environ.get(
    "MODEL_OUTPUT_PATH", os.path.join(REPO_ROOT, "models", "roi_early_stage_model.joblib")
)
METADATA_OUTPUT_PATH = os.environ.get(
    "METADATA_OUTPUT_PATH", os.path.join(REPO_ROOT, "reports", "roi_model_metadata.json")
)


def _build_preprocessor(categorical_cols, numeric_cols):
    return ColumnTransformer(
        transformers=[
            ("categorical", OneHotEncoder(handle_unknown="ignore"), categorical_cols),
            ("numeric", "passthrough", numeric_cols),
        ]
    )


def _evaluate(model, X_test, y_test):
    preds = model.predict(X_test)
    return {
        "r2": float(r2_score(y_test, preds)),
        "mae": float(mean_absolute_error(y_test, preds)),
        "rmse": float(np.sqrt(mean_squared_error(y_test, preds))),
    }


def train_early_stage_model(df: pd.DataFrame):
    X = df[EARLY_STAGE_FEATURES]
    y = df[TARGET]
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=RANDOM_STATE)

    pipeline = Pipeline(
        steps=[
            ("preprocessor", _build_preprocessor(CATEGORICAL_FEATURES, NUMERIC_FEATURES)),
            ("model", RandomForestRegressor(
                n_estimators=150, max_depth=14, random_state=RANDOM_STATE, n_jobs=1
            )),
        ]
    )
    pipeline.fit(X_train, y_train)
    metrics = _evaluate(pipeline, X_test, y_test)
    return pipeline, metrics, len(X_train), len(X_test)


def train_cost_only_model(df: pd.DataFrame):
    X = df[["Acquisition_Cost"]]
    y = df[TARGET]
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=RANDOM_STATE)

    pipeline = Pipeline(
        steps=[
            ("preprocessor", ColumnTransformer([("numeric", "passthrough", ["Acquisition_Cost"])])),
            ("model", RandomForestRegressor(
                n_estimators=150, max_depth=14, random_state=RANDOM_STATE, n_jobs=1
            )),
        ]
    )
    pipeline.fit(X_train, y_train)
    metrics = _evaluate(pipeline, X_test, y_test)
    return metrics


def train_strategy_only_model(df: pd.DataFrame):
    X = df[CATEGORICAL_FEATURES]
    y = df[TARGET]
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=RANDOM_STATE)

    pipeline = Pipeline(
        steps=[
            ("preprocessor", ColumnTransformer([("categorical", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES)])),
            ("model", LinearRegression()),
        ]
    )
    pipeline.fit(X_train, y_train)
    metrics = _evaluate(pipeline, X_test, y_test)
    return metrics


def main():
    if not os.path.exists(DATA_PATH):
        raise FileNotFoundError(
            f"Dataset not found at {DATA_PATH}. Set DATA_PATH env var or place the cleaned CSV there."
        )

    df = pd.read_csv(DATA_PATH)
    missing = [c for c in EARLY_STAGE_FEATURES + [TARGET] if c not in df.columns]
    if missing:
        raise ValueError(f"Dataset is missing required columns: {missing}")

    df = df.dropna(subset=EARLY_STAGE_FEATURES + [TARGET])

    print(f"Loaded {len(df)} rows from {DATA_PATH}")

    print("Training early-stage Random Forest (primary model)...")
    pipeline, early_stage_metrics, train_n, test_n = train_early_stage_model(df)
    print("  ->", early_stage_metrics)

    print("Training cost-only Random Forest (reference)...")
    cost_only_metrics = train_cost_only_model(df)
    print("  ->", cost_only_metrics)

    print("Training strategy-only Linear Regression (reference)...")
    strategy_only_metrics = train_strategy_only_model(df)
    print("  ->", strategy_only_metrics)

    os.makedirs(os.path.dirname(MODEL_OUTPUT_PATH), exist_ok=True)
    joblib.dump(pipeline, MODEL_OUTPUT_PATH)
    print(f"Saved primary model pipeline to {MODEL_OUTPUT_PATH}")

    additional_r2_from_early_stage_features = (
        early_stage_metrics["r2"] - cost_only_metrics["r2"]
    )

    metadata = {
        "model_name": "Random Forest (early-stage)",
        "prediction_type": "early_stage",
        "features": EARLY_STAGE_FEATURES,
        "categorical_features": CATEGORICAL_FEATURES,
        "numeric_features": NUMERIC_FEATURES,
        "target": TARGET,
        "train_sample_count": train_n,
        "test_sample_count": test_n,
        "total_sample_count": len(df),
        "random_state": RANDOM_STATE,
        "training_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "metrics": {
            "r2": early_stage_metrics["r2"],
            "mae": early_stage_metrics["mae"],
            "rmse": early_stage_metrics["rmse"],
        },
        "model_comparison": {
            "strategy_only": {
                "model_name": "Linear Regression (strategy-only)",
                "features": CATEGORICAL_FEATURES,
                **strategy_only_metrics,
            },
            "cost_only": {
                "model_name": "Random Forest (cost-only)",
                "features": ["Acquisition_Cost"],
                **cost_only_metrics,
            },
            "early_stage": {
                "model_name": "Random Forest (early-stage)",
                "features": EARLY_STAGE_FEATURES,
                **early_stage_metrics,
            },
        },
        "additional_r2_from_early_stage_features_vs_cost_only": additional_r2_from_early_stage_features,
        "dominant_feature_note": (
            "Acquisition_Cost explains most of the early-stage model's predictive power. "
            "Model predictions are decision-support estimates, not evidence that campaign "
            "strategy independently causes ROI."
        ),
    }

    os.makedirs(os.path.dirname(METADATA_OUTPUT_PATH), exist_ok=True)
    with open(METADATA_OUTPUT_PATH, "w") as f:
        json.dump(metadata, f, indent=2)
    print(f"Saved metadata to {METADATA_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
