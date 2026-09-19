"""
Environment-based configuration for the Marketing ROI Intelligence Platform.

Values are read from environment variables (see .env.example). SQLite is
used initially; DATABASE_URL is read so PostgreSQL can be swapped in later
without changing application code.
"""

import os


class BaseConfig:
    DEBUG = False
    TESTING = False

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")

    # Dataset location — Phase 1 only reads this path; it does not copy
    # or duplicate the dataset anywhere in the repository.
    DATA_PATH = os.environ.get(
        "DATA_PATH",
        os.path.join("data", "cleaned", "marketing_campaign_cleaned.csv"),
    )

    MODEL_DIR = os.environ.get("MODEL_DIR", "models")
    MODEL_PATH = os.environ.get("MODEL_PATH", os.path.join(MODEL_DIR, "roi_early_stage_model.joblib"))
    MODEL_METADATA_PATH = os.environ.get(
        "MODEL_METADATA_PATH", os.path.join("reports", "roi_model_metadata.json")
    )

    DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///marketing_roi.db")

    JSON_SORT_KEYS = False


class DevelopmentConfig(BaseConfig):
    DEBUG = True


class ProductionConfig(BaseConfig):
    DEBUG = False


class TestingConfig(BaseConfig):
    TESTING = True
    DEBUG = True


_CONFIGS = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}


def get_config(name: str | None = None):
    """Return the config class for the given environment name.

    Falls back to FLASK_ENV / defaults to development if not specified.
    """
    name = name or os.environ.get("FLASK_ENV", "development")
    return _CONFIGS.get(name, DevelopmentConfig)
