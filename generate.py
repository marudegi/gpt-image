"""
GPT Image (OpenAI 画像生成) 基盤スクリプト

使用モデル:
  - gpt-image-2  (OpenAI 画像生成: 高品質・指示追従に強い)

呼び出し方は gemini-image/generate.py と揃えてある（generate_image / edit_image）。
"""

import base64
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(Path(__file__).parent / ".env")

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# 散発的なAPIストール対策：タイムアウト（秒）＋自動リトライ。環境変数で上書き可。
DEFAULT_TIMEOUT_S = float(os.environ.get("OPENAI_TIMEOUT_S", "180"))
MAX_RETRIES = int(os.environ.get("OPENAI_MAX_RETRIES", "3"))


def _client() -> OpenAI:
    # timeout 超過時は OpenAI SDK が max_retries の範囲で自動再試行する
    return OpenAI(
        api_key=os.environ["OPENAI_API_KEY"],
        timeout=DEFAULT_TIMEOUT_S,
        max_retries=MAX_RETRIES,
    )


def _save(data, prefix: str) -> list[Path]:
    timestamp = datetime.now().strftime("%Y.%m.%d_%H%M%S")
    full_prefix = f"{timestamp}_{prefix}" if prefix else timestamp
    saved_paths = []
    for img_index, item in enumerate(data):
        save_path = OUTPUT_DIR / f"{full_prefix}_{img_index:02d}.png"
        save_path.write_bytes(base64.b64decode(item.b64_json))
        saved_paths.append(save_path)
        print(f"保存: {save_path}")
    return saved_paths


def generate_image(
    prompt: str,
    model: str = "gpt-image-2",
    size: str = "1024x1024",
    quality: str = "high",
    n: int = 1,
    filename_prefix: str = "",
) -> list[Path]:
    """テキストプロンプトから画像を生成する。

    Args:
        prompt: 画像生成プロンプト（日本語可）
        model: 使用するモデルID
        size: "1024x1024"(正方) / "1536x1024"(横) / "1024x1536"(縦) / "auto"
        quality: "low" / "medium" / "high" / "auto"
        n: 生成枚数
        filename_prefix: 保存ファイル名の接頭辞

    Returns:
        保存された画像ファイルのパスリスト
    """
    response = _client().images.generate(
        model=model,
        prompt=prompt,
        size=size,
        quality=quality,
        n=n,
    )
    return _save(response.data, filename_prefix)


def edit_image(
    prompt: str,
    input_image_path: str | Path,
    model: str = "gpt-image-2",
    size: str = "1024x1024",
    quality: str = "high",
    filename_prefix: str = "edit",
) -> list[Path]:
    """既存の画像をプロンプトで編集する。

    Args:
        prompt: 編集指示プロンプト
        input_image_path: 入力画像のパス（PNG/JPG/WebP）
        model: 使用するモデルID
        size: 出力サイズ
        quality: 出力品質
        filename_prefix: 保存ファイル名の接頭辞

    Returns:
        保存された画像ファイルのパスリスト
    """
    with open(input_image_path, "rb") as f:
        response = _client().images.edit(
            model=model,
            image=f,
            prompt=prompt,
            size=size,
            quality=quality,
        )
    return _save(response.data, filename_prefix)


if __name__ == "__main__":
    # 動作確認サンプル
    print("=== GPT Image 画像生成テスト ===")
    paths = generate_image(
        prompt="美しい日本の桜の庭園。夕暮れ時の柔らかい光、池に映る桜の花びら。写真リアル。",
        size="1536x1024",
        quality="medium",
        filename_prefix="sakura_test",
    )
    print(f"\n生成完了: {len(paths)} 枚")
    for p in paths:
        print(f"  → {p}")
