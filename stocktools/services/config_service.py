from __future__ import annotations

from pathlib import Path

from stocktools.config.model_config_repo import ModelConfigRepo


class ConfigService:
    def __init__(self, config_db_path: Path | str):
        self.model_config_repo = ModelConfigRepo(config_db_path)

    def set_model(self, base_url: str, api_key: str, model_name: str) -> dict:
        return self.model_config_repo.upsert(base_url, api_key, model_name)

    def get_model(self) -> dict | None:
        return self.model_config_repo.get()
