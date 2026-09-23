# GPT Image 画像生成基盤

OpenAI の `gpt-image-2`（既定）／`gpt-image-2.5-flare`／`gpt-image-2.5-sunburst` を使った画像生成・編集の基盤スクリプトです。
呼び出し方は隣の `gemini-image` と揃えてあります
（`generate_image` / `edit_image`、`output_dir` / `save_prompt` / `filename_prefix`）。
検索グラウンディング付き生成（`generate_with_search`）は gemini-image 側のみです。

## セットアップ

```bash
cd gpt-image
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
# .env を編集して OPENAI_API_KEY を設定
```

## 使い方

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / "Developer/tools/gpt-image"))
from generate import generate_image, edit_image

# テキストから画像生成（size 既定 "16:9" = 2048x1152）
paths = generate_image(
    prompt="美しい富士山の夜景。星空と湖に映る反射。",
    size="16:9",
    quality="high",
    filename_prefix="fuji",
    output_dir="~/Developer/work/<依頼元の関連Dir>",  # 未指定なら output/
)

# 画像編集（size 既定 "auto" ＝入力画像に合わせる）
paths = edit_image(
    prompt="背景を桜の花びらが舞う春の公園に変更して",
    input_image_path="output/your_image.png",
)
```

CLI で単発実行（動作確認サンプル）:

```bash
.venv/bin/python generate.py
```

## パラメータ

| 項目 | 指定値 |
|---|---|
| `size` | プリセット名：`16:9`（既定＝2048x1152）／`slide`（＝2112x1280、PPT 30cm×18.2cm 全面貼付用）／`16:10`（＝2048x1280）／`3:2`（＝1536x1024）／`1:1`／`9:16`／`4:3`／`21:9` ほか。任意の `WIDTHxHEIGHT`（**16の倍数**・比率1:3〜3:1・総ピクセル数 655,360〜8,294,400・最大3840x2160）や `auto` も可 |
| `quality` | `low` / `medium` / `high`（既定） / `auto`。gpt-image-2.5 系のみ `xhigh` / `max` も可（高コスト） |
| `n` | 生成枚数 1〜10 |
| `model` | `gpt-image-2`（既定。`.env` の `OPENAI_IMAGE_MODEL` で変更可）／`gpt-image-2.5-flare`／`gpt-image-2.5-sunburst`。任意解像度は gpt-image-2 系（2.5 含む）のみ（gpt-image-1 は固定3サイズ＋auto） |
| `output_dir` | 出力先。案件向けは依頼元の関連Dirを渡す（`~` 展開対応）。未指定なら `output/` |
| `save_prompt` | 既定 True。画像と同名の `.md` にプロンプト・サイズ・実寸を記録 |
| `filename_prefix` | 保存ファイル名の接頭辞（日時は自動付与） |
| `background` | キーワード指定。`transparent` / `opaque` / `auto`。未指定なら API 既定。透過は gpt-image-2.5 系で正式対応、gpt-image-2 は preview |
| `input_fidelity` | `edit_image` のみ・キーワード指定。`high` / `low`。対応モデルのみ有効（gpt-image-2 は無視） |

### モデルの選び方（2026-09 時点）

| モデル | 向き | 備考 |
|---|---|---|
| `gpt-image-2` | 既定・実績あり | 透過背景は preview、`input_fidelity` は無視 |
| `gpt-image-2.5-flare` | 日常用途（スライド挿絵など） | gpt-image-2 より高速・高品質とされる。`xhigh`/`max`・透過背景に対応 |
| `gpt-image-2.5-sunburst` | 細部・編集の制御を重視する制作物 | `xhigh`/`max`・透過背景に対応 |

再現性を固定したい案件ではスナップショット ID（`gpt-image-2-2026-04-21`、`gpt-image-2.5-flare-2026-09-08` 等）を `model` に渡す。

## 出力

生成画像は `YYYY.MM.DD_HHMMSS_prefix_00.png` 形式で保存されます。
`save_prompt=True`（既定）なら、同名の `.md`（プロンプト・モデル・サイズ・実寸）が画像の隣に残ります。

**成果物は依頼元の関連ディレクトリに、プロンプト `.md` を添えて置く**（`output_dir` 引数で直接保存）。
絶対パスをコードに固定しない。汎用置き場は `output/`（`.gitignore` 済み）。

## 運用の注意

- **gemini-image と同時並列で実行しない**（並列時に Gemini 側がストールした実績あり）。複数モデルは逐次実行する
- タイムアウト（`OPENAI_TIMEOUT_S` 既定180秒）・自動リトライ（`OPENAI_MAX_RETRIES` 既定3回）は `.env` で調整可
- 既定モデルは `.env` の `OPENAI_IMAGE_MODEL` で切替可（例：`gpt-image-2.5-flare`）。コード側で `model=` を渡せばそちらが優先

## 認証

`.env` の `OPENAI_API_KEY` を使用（`python-dotenv` で読み込み）。
`.env` は `.gitignore` 済みで追跡されません。バックアップは `~/.secrets/openai_api_key`。
