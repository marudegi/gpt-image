# GPT Image 画像生成基盤

OpenAI の `gpt-image-2` を使った画像生成・編集の基盤スクリプトです。
呼び出し方は隣の `gemini-image` と揃えてあります（`generate_image` / `edit_image`）。

## セットアップ

```bash
cd openai-image
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
# .env を編集して OPENAI_API_KEY を設定
```

## 使い方

```python
from generate import generate_image, edit_image

# テキストから画像生成
paths = generate_image(
    prompt="美しい富士山の夜景。星空と湖に映る反射。",
    size="1536x1024",   # 横長
    quality="high",
)

# 画像編集
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
| `size` | `1024x1024`(正方) / `1536x1024`(横) / `1024x1536`(縦) / `auto` |
| `quality` | `low` / `medium` / `high` / `auto` |
| `model` | `gpt-image-2`（既定）。新モデルが出たらここを差し替え |

## 出力

生成画像は `output/` フォルダに `YYYY.MM.DD_HHMMSS_prefix_00.png` 形式で保存されます。

## 認証

`.env` の `OPENAI_API_KEY` を使用（`python-dotenv` で読み込み）。
`.env` は `.gitignore` 済みで追跡されません。バックアップは `~/.secrets/openai_api_key`。
