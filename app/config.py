"""設定・環境変数の読込（詳細設計§9）。

- APIキーは環境変数からのみ読む。ファイル・既定値には保持しない。
- キー値はログ・print・例外メッセージに一切含めない。
"""

import os
from dataclasses import dataclass

# モデル名の既定値はここ1か所で差し替え可能にする（コードに最終決定値を散らさない）。
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_DB_PATH = "bluewing.db"


class ConfigError(Exception):
    """設定不備を表す例外。メッセージにキー値は含めない。"""


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    openai_model: str
    db_path: str


def get_settings() -> Settings:
    """環境変数から設定を読み取る。OPENAI_API_KEY 未設定なら停止する。"""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        # 誘導のみ。キー値は当然含めない。
        raise ConfigError(
            "OPENAI_API_KEY が未設定です。"
            'PowerShell で設定してください: $env:OPENAI_API_KEY = "（各自のキー）"'
        )

    return Settings(
        openai_api_key=api_key,
        openai_model=os.environ.get("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL,
        db_path=os.environ.get("BLUEWING_DB_PATH") or DEFAULT_DB_PATH,
    )
