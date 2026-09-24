"""
GPT Image (OpenAI 画像生成) 基盤スクリプト

使用モデル:
  - gpt-image-2.5-flare    (既定。2026-09 追加。日常用途向け・gpt-image-2 より高速)
  - gpt-image-2            (旧既定。透過背景は preview、input_fidelity は無視)
  - gpt-image-2.5-sunburst (2026-09 追加。細部・編集の制御を重視する用途向け)
  既定モデルは .env の OPENAI_IMAGE_MODEL で切り替えられる。

呼び出し方は gemini-image/generate.py と揃えてある
（generate_image / edit_image、output_dir / save_prompt / filename_prefix）。

gpt-image-2 系（2.5 含む）は任意解像度を "WIDTHxHEIGHT" で指定できる
（幅・高さとも16の倍数、アスペクト比 1:3〜3:1、総ピクセル数 655,360〜8,294,400、
最大 3840x2160）。よく使う比率は SIZE_PRESETS のキー（"16:9" 等）で指定するのが簡単。
"""

import base64
import os
import re
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(Path(__file__).parent / ".env")

OUTPUT_DIR = Path(__file__).parent / "output"

# 散発的なAPIストール対策：タイムアウト（秒）＋自動リトライ。環境変数で上書き可。
DEFAULT_TIMEOUT_S = float(os.environ.get("OPENAI_TIMEOUT_S", "180"))
MAX_RETRIES = int(os.environ.get("OPENAI_MAX_RETRIES", "3"))

# 既定モデル。.env の OPENAI_IMAGE_MODEL で上書き可（例: gpt-image-2 に戻す）
DEFAULT_MODEL = os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-2.5-flare")

# 比率名 → gpt-image-2 の実サイズ（すべて16の倍数）
SIZE_PRESETS = {
    "16:9": "2048x1152",   # 横長スライド標準（既定）
    "16:10": "2048x1280",
    "slide": "2112x1280",  # PPT 30cm×18.2cm（比率1.648）全面貼付用
    "3:2": "1536x1024",
    "2:3": "1024x1536",
    "1:1": "1024x1024",
    "9:16": "1152x2048",
    "4:3": "1600x1200",
    "3:4": "1200x1600",
    "21:9": "2352x1008",
}
DEFAULT_SIZE = "16:9"

# gpt-image-1 系は固定サイズのみ（任意解像度は gpt-image-2 系のみ）
_GPT_IMAGE_1_SIZES = {"1024x1024", "1536x1024", "1024x1536", "auto"}
VALID_QUALITIES = {"low", "medium", "high", "auto"}
# gpt-image-2.5 系のみ追加で指定できる品質（高コスト）
_GPT_IMAGE_25_EXTRA_QUALITIES = {"xhigh", "max"}
VALID_BACKGROUNDS = {"transparent", "opaque", "auto"}
VALID_INPUT_FIDELITIES = {"high", "low"}


def _is_gpt_image_25(model: str) -> bool:
    return model.startswith("gpt-image-2.5")


def _require_api_key() -> str:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError(
            "OPENAI_API_KEY が未設定です。"
            "~/Developer/tools/gpt-image/.env に設定してください"
            "（バックアップ: ~/.secrets/openai_api_key）"
        )
    return key


def _client() -> OpenAI:
    # timeout 超過時は OpenAI SDK が max_retries の範囲で自動再試行する
    # （接続エラー・タイムアウト・429・5xx が対象。課金上限等の 400 は即失敗）
    return OpenAI(
        api_key=_require_api_key(),
        timeout=DEFAULT_TIMEOUT_S,
        max_retries=MAX_RETRIES,
    )


def _resolve_size(size: str, model: str) -> str:
    """プリセット名（"16:9" 等）・実サイズ・"auto" を検証して実サイズ文字列に解決する。"""
    if size is None or size == "auto":
        return "auto"
    s = SIZE_PRESETS.get(str(size).strip(), str(size).strip())

    if model.startswith("dall-e"):
        raise ValueError("dall-e 系モデルは本ツールでは非対応です（gpt-image 系を使用してください）")
    if model.startswith("gpt-image-1"):
        if s not in _GPT_IMAGE_1_SIZES:
            raise ValueError(
                f"{model} のサイズは {sorted(_GPT_IMAGE_1_SIZES)} のみです（任意解像度は gpt-image-2 系のみ）"
            )
        return s

    m = re.fullmatch(r"(\d+)x(\d+)", s)
    if not m:
        raise ValueError(
            f"size '{size}' が不正です。プリセット名 {sorted(SIZE_PRESETS)} か "
            f"'WIDTHxHEIGHT'（16の倍数）または 'auto' を指定してください"
        )
    w, h = int(m.group(1)), int(m.group(2))
    if w % 16 or h % 16:
        raise ValueError(f"幅・高さは16の倍数が必要です: {s}（例: 16:9 なら 2048x1152）")
    if not (1 / 3 <= w / h <= 3):
        raise ValueError(f"アスペクト比は 1:3〜3:1 の範囲で指定してください: {s}")
    if not (655_360 <= w * h <= 8_294_400):
        raise ValueError(f"総ピクセル数は 655,360〜8,294,400 の範囲です: {s} = {w * h:,}px")
    if max(w, h) > 3840:
        raise ValueError(f"最大 3840x2160 までです: {s}")
    if w * h > 2560 * 1440:
        print(f"[warn] {s} は 2560x1440 超のため experimental 帯です（{model}）")
    return s


def _validate_quality(quality: str, model: str) -> str:
    valid = VALID_QUALITIES | _GPT_IMAGE_25_EXTRA_QUALITIES if _is_gpt_image_25(model) else VALID_QUALITIES
    if quality not in valid:
        hint = "（xhigh / max は gpt-image-2.5 系のみ）" if quality in _GPT_IMAGE_25_EXTRA_QUALITIES else ""
        raise ValueError(f"quality '{quality}' が不正です。{model} の有効値: {sorted(valid)}{hint}")
    return quality


def _validate_background(background: str | None, model: str) -> str | None:
    if background is None:
        return None
    if background not in VALID_BACKGROUNDS:
        raise ValueError(f"background '{background}' が不正です。有効値: {sorted(VALID_BACKGROUNDS)}")
    if background == "transparent" and model.startswith("gpt-image-2") and not _is_gpt_image_25(model):
        print(f"[warn] {model} の透過背景は preview 扱いです（安定して使うなら gpt-image-2.5 系）")
    return background


def _drop_none(**kwargs) -> dict:
    """未指定（None）の任意パラメータは送らず API の既定値に任せる。"""
    return {k: v for k, v in kwargs.items() if v is not None}


def _sanitize_prefix(prefix: str) -> str:
    """ファイル名に使えない文字・空白を '_' に置換する。"""
    return re.sub(r'[\\/:*?"<>|\s]+', "_", prefix).strip("_")


def _save(
    data,
    filename_prefix: str,
    out_dir: Path,
    save_prompt: bool,
    prompt: str,
    model: str,
    size: str,
    quality: str,
    background: str | None = None,
) -> list[Path]:
    if not data:
        raise RuntimeError("画像が生成されませんでした（APIレスポンスが空）")
    timestamp = datetime.now().strftime("%Y.%m.%d_%H%M%S")
    prefix = f"{timestamp}_{_sanitize_prefix(filename_prefix)}" if filename_prefix else timestamp
    saved_paths = []
    for img_index, item in enumerate(data):
        if item.b64_json is None:
            raise RuntimeError("APIレスポンスに画像データ（b64_json）がありません")
        save_path = out_dir / f"{prefix}_{img_index:02d}.png"
        save_path.write_bytes(base64.b64decode(item.b64_json))
        saved_paths.append(save_path)
        try:
            from PIL import Image
            with Image.open(save_path) as im:
                actual = f"{im.size[0]}x{im.size[1]}"
        except Exception:  # noqa: BLE001 実寸確認は補助情報なので失敗しても保存は成立させる
            actual = "不明"
        print(f"保存: {save_path}（実寸 {actual}px）")
        if save_prompt:
            prompt_md = save_path.with_suffix(".md")
            prompt_md.write_text(
                f"# 画像生成プロンプト\n\n"
                f"- 生成日時: {timestamp}\n"
                f"- モデル: {model}\n"
                f"- サイズ: {size} / 品質: {quality}"
                f"{f' / 背景: {background}' if background else ''}\n"
                f"- 実寸: {actual}px\n"
                f"- 画像: `{save_path.name}`\n\n"
                f"## prompt\n\n{prompt}\n",
                encoding="utf-8",
            )
            print(f"保存: {prompt_md}")
    return saved_paths


def _resolve_out_dir(output_dir: str | Path | None) -> Path:
    out_dir = Path(output_dir).expanduser() if output_dir else OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def generate_image(
    prompt: str,
    model: str = DEFAULT_MODEL,
    size: str = DEFAULT_SIZE,
    quality: str = "high",
    n: int = 1,
    filename_prefix: str = "",
    output_dir: str | Path | None = None,
    save_prompt: bool = True,
    *,
    background: str | None = None,
) -> list[Path]:
    """テキストプロンプトから画像を生成する。

    Args:
        prompt: 画像生成プロンプト（日本語可）
        model: 使用するモデルID（既定 gpt-image-2.5-flare。.env の OPENAI_IMAGE_MODEL で変更可）。
               gpt-image-2.5-sunburst / gpt-image-2 も指定可
        size: プリセット名（"16:9"(既定)=2048x1152 / "slide"=2112x1280(PPT 30x18.2cm) /
              "3:2"=1536x1024 / "1:1" / "9:16" 等）、任意の "WIDTHxHEIGHT"（16の倍数・
              比率1:3〜3:1・総px 655,360〜8,294,400・最大3840x2160）、または "auto"
        quality: "low" / "medium" / "high" / "auto"。gpt-image-2.5 系は "xhigh" / "max" も可
        n: 生成枚数（1〜10）
        filename_prefix: 保存ファイル名の接頭辞
        output_dir: 出力先ディレクトリ。未指定なら既定の output/。
                    依頼元の関連ディレクトリを渡すと成果物をそこに置ける（~ 展開対応）
        save_prompt: True のとき、使用したプロンプトを画像と同名の .md で隣に残す
        background: "transparent" / "opaque" / "auto"。未指定なら API 既定（auto）。
                    透過は gpt-image-2.5 系で正式対応、gpt-image-2 は preview

    Returns:
        保存された画像ファイルのパスリスト
    """
    resolved_size = _resolve_size(size, model)
    _validate_quality(quality, model)
    _validate_background(background, model)
    if not 1 <= n <= 10:
        raise ValueError(f"n は 1〜10 の範囲で指定してください: {n}")
    out_dir = _resolve_out_dir(output_dir)

    response = _client().images.generate(
        model=model,
        prompt=prompt,
        size=resolved_size,
        quality=quality,
        n=n,
        **_drop_none(background=background),
    )
    return _save(response.data, filename_prefix, out_dir, save_prompt,
                 prompt, model, resolved_size, quality, background)


def edit_image(
    prompt: str,
    input_image_path: str | Path,
    model: str = DEFAULT_MODEL,
    size: str = "auto",
    quality: str = "high",
    *,  # n 以降はキーワード指定のみ（旧シグネチャの位置引数と衝突させない）
    n: int = 1,
    filename_prefix: str = "edit",
    output_dir: str | Path | None = None,
    save_prompt: bool = True,
    background: str | None = None,
    input_fidelity: str | None = None,
) -> list[Path]:
    """既存の画像をプロンプトで編集する。

    Args:
        prompt: 編集指示プロンプト
        input_image_path: 入力画像のパス（PNG/JPG/WebP）
        model: 使用するモデルID
        size: 出力サイズ。既定 "auto"（入力画像に合わせる）。
              generate_image と同じプリセット名・"WIDTHxHEIGHT" も指定可
        quality: 出力品質（gpt-image-2.5 系は "xhigh" / "max" も可）
        n: 生成枚数（1〜10）
        filename_prefix: 保存ファイル名の接頭辞
        output_dir: 出力先ディレクトリ（未指定なら既定の output/。~ 展開対応）
        save_prompt: True のとき、使用したプロンプトを画像と同名の .md で隣に残す
        background: generate_image と同じ（"transparent" / "opaque" / "auto"）
        input_fidelity: 入力画像への忠実度 "high" / "low"。未指定なら API 既定。
                        対応モデルのみ有効（gpt-image-2 は無視する）

    Returns:
        保存された画像ファイルのパスリスト
    """
    input_image_path = Path(input_image_path).expanduser()
    if not input_image_path.exists():
        raise FileNotFoundError(f"入力画像が見つかりません: {input_image_path}")

    resolved_size = _resolve_size(size, model)
    _validate_quality(quality, model)
    _validate_background(background, model)
    if input_fidelity is not None and input_fidelity not in VALID_INPUT_FIDELITIES:
        raise ValueError(
            f"input_fidelity '{input_fidelity}' が不正です。有効値: {sorted(VALID_INPUT_FIDELITIES)}"
        )
    if not 1 <= n <= 10:
        raise ValueError(f"n は 1〜10 の範囲で指定してください: {n}")
    out_dir = _resolve_out_dir(output_dir)

    with open(input_image_path, "rb") as f:
        response = _client().images.edit(
            model=model,
            image=f,
            prompt=prompt,
            size=resolved_size,
            quality=quality,
            n=n,
            **_drop_none(background=background, input_fidelity=input_fidelity),
        )
    return _save(response.data, filename_prefix, out_dir, save_prompt,
                 f"{prompt}\n\n（入力画像: {input_image_path}）", model, resolved_size, quality,
                 background)


if __name__ == "__main__":
    # 動作確認サンプル
    print("=== GPT Image 画像生成テスト ===")
    paths = generate_image(
        prompt="美しい日本の桜の庭園。夕暮れ時の柔らかい光、池に映る桜の花びら。写真リアル。",
        size="16:9",
        quality="medium",
        filename_prefix="sakura_test",
    )
    print(f"\n生成完了: {len(paths)} 枚")
    for p in paths:
        print(f"  → {p}")
