from __future__ import annotations

from pathlib import Path

from stocktools.config.model_config_repo import ModelConfigRepo
from stocktools.infra.paths import Paths


class LLMClient:
    def __init__(self, config_db_path: Path | str | None = None, timeout: float = 60.0):
        self.config_db_path = config_db_path or Paths.resolve().config_path
        self.timeout = timeout

    def invoke(self, messages: list[dict[str, str]], temperature: float = 0.2) -> str:
        config = ModelConfigRepo(self.config_db_path).get()
        if not config:
            raise RuntimeError("缺少模型配置，请先运行 setup.sh 配置 base_url、api_key 和 model_name")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("缺少 openai 依赖，请先安装 requirements.txt") from exc
        client = OpenAI(base_url=config["base_url"], api_key=config["api_key"], timeout=self.timeout)
        response = client.chat.completions.create(
            model=config["model_name"],
            messages=messages,
            temperature=temperature,
            stream=False,
        )
        return response.choices[0].message.content or ""

