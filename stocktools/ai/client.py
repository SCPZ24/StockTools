from __future__ import annotations

from openai import OpenAI

from pathlib import Path

from stocktools.config.model_config_repo import ModelConfigRepo
from stocktools.infra.paths import Paths


class LLMClient:
    def __init__(self, config_db_path: Path | str | None = None, timeout: float = 60.0):
        config = ModelConfigRepo(config_db_path or Paths.resolve().config_path).get()
        if not config:
            raise RuntimeError("缺少模型配置，请先运行 setup.sh 配置 base_url、api_key 和 model_name")

        self.model_name: str = config["model_name"]
        self._client = OpenAI(base_url=config["base_url"], api_key=config["api_key"], timeout=timeout)

    def invoke(self, messages: list[dict[str, str]], temperature: float = 0.2) -> str:
        response = self._client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=temperature,
            stream=False,
        )
        return response.choices[0].message.content or ""

