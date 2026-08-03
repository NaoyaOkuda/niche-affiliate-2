#!/usr/bin/env python3
"""Claude APIで新しい記事を生成し、sites/<id>/content/ に保存する。

使い方:
    ANTHROPIC_API_KEY=sk-... python3 engine/generate.py            # 全サイト
    ANTHROPIC_API_KEY=sk-... python3 engine/generate.py <site_id>  # 特定サイト

site.json の topicsQueue から先頭のトピックを取り出して記事化し、
topicsDone に移動する。キューが空の場合は新トピック案の生成も行う。
"""
import json
import os
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITES_DIR = ROOT / "sites"
API_URL = "https://api.anthropic.com/v1/messages"
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")

ARTICLE_PROMPT = """あなたは{niche}の専門ライターです。以下のトピックでアフィリエイトサイト用の記事を書いてください。

# サイト情報
- サイト名: {title}
- 読者: {audience}

# トピック
{topic}

# 執筆ルール(厳守)
- 2500〜3500字程度。「## 見出し」で構成を分け、最後に「## まとめ」を置く
- 誠実に書く。体験談の捏造・大げさな効果の断定・「絶対」「必ず」等の表現は禁止
- 医療的な判断が必要な話題は「獣医師に相談を」と案内する
- 商品を紹介する箇所には、本文中の独立した行に {{{{product:1}}}} {{{{product:2}}}} のような
  プレースホルダーを置く(商品は2〜4個)。商品名の直接のURL記載は不要
- 比較が有効な場合はMarkdownの表を使う
- 広告表記(PR文)はテンプレートが自動挿入するので本文には書かない

# 出力形式
以下のJSONのみを出力すること(コードフェンス無し):
{{
  "slug": "英小文字とハイフンのURLスラッグ",
  "title": "記事タイトル(32字以内、検索キーワードを含める)",
  "description": "メタディスクリプション(80〜110字)",
  "category": "カテゴリ名(ハリネズミ/デグー等の短い分類)",
  "image_prompt": "この記事のアイキャッチ写真を生成するための英語プロンプト(動物や用品の温かく可愛い情景。テキスト・ロゴは入れない)",
  "products": [
    {{"name": "商品の一般名称", "keyword": "楽天検索用キーワード", "note": "一言メモ"}}
  ],
  "body": "Markdown本文(タイトルのh1は含めない。##から始める)"
}}
"""

GEMINI_MODEL = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image-preview")


def generate_eyecatch(site_dir, slug, image_prompt):
    """GeminiでアイキャッチをJPEG生成して assets/ に保存。GEMINI_API_KEY未設定なら何もしない"""
    import base64

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key or not image_prompt:
        return None
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{GEMINI_MODEL}:generateContent?key={urllib.parse.quote(api_key)}")
    prompt = image_prompt + " Photorealistic, warm cozy tones, no text or logos, 16:9 wide composition."
    bodies = [
        {"contents": [{"parts": [{"text": prompt}]}],
         "generationConfig": {"responseModalities": ["TEXT", "IMAGE"],
                              "imageConfig": {"aspectRatio": "16:9"}}},
        # 一部モデルはimageConfig非対応のため、失敗時は最小構成で再試行
        {"contents": [{"parts": [{"text": prompt}]}],
         "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]}},
    ]
    for body in bodies:
        try:
            req = urllib.request.Request(
                url, data=json.dumps(body).encode("utf-8"),
                headers={"content-type": "application/json"})
            with urllib.request.urlopen(req, timeout=300) as res:
                data = json.loads(res.read().decode("utf-8"))
            for part in data["candidates"][0]["content"]["parts"]:
                inline = part.get("inlineData") or part.get("inline_data")
                if inline and inline.get("data"):
                    assets = site_dir / "assets"
                    assets.mkdir(exist_ok=True)
                    name = f"eyecatch-{slug}.jpg"
                    (assets / name).write_bytes(base64.b64decode(inline["data"]))
                    print(f"  ✓ アイキャッチ生成: assets/{name}")
                    return name
        except Exception as e:
            print(f"  ⚠ アイキャッチ生成に失敗({e})— 次の設定で再試行/スキップ")
    return None


def call_claude(prompt):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("環境変数 ANTHROPIC_API_KEY を設定してください")
    req = urllib.request.Request(
        API_URL,
        data=json.dumps({
            "model": MODEL,
            "max_tokens": 8000,
            "messages": [{"role": "user", "content": prompt}],
        }).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    with urllib.request.urlopen(req, timeout=300) as res:
        data = json.loads(res.read().decode("utf-8"))
    return "".join(b.get("text", "") for b in data["content"])


def parse_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1])


def yaml_quote(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def write_article(site_dir, article, image_name=None):
    today = date.today().isoformat()
    slug = re.sub(r"[^a-z0-9-]", "", article["slug"].lower()) or "article"
    products = "\n".join(
        f"  - name: {yaml_quote(p['name'])}\n    keyword: {yaml_quote(p['keyword'])}\n    note: {yaml_quote(p.get('note', ''))}"
        for p in article.get("products", [])
    )
    image_line = f"image: {yaml_quote(image_name)}\n" if image_name else ""
    fm = (
        f"---\n"
        f"title: {yaml_quote(article['title'])}\n"
        f"description: {yaml_quote(article['description'])}\n"
        f"date: {today}\n"
        f"category: {yaml_quote(article.get('category', ''))}\n"
        f"{image_line}"
        f"products:\n{products}\n"
        f"---\n\n"
    )
    path = site_dir / "content" / f"{today}-{slug}.md"
    path.write_text(fm + article["body"].strip() + "\n", encoding="utf-8")
    return path


def generate_for_site(site_dir):
    site_file = site_dir / "site.json"
    site = json.loads(site_file.read_text(encoding="utf-8"))
    n = site.get("articlesPerRun", 1)
    queue = site.get("topicsQueue", [])
    if not queue:
        print(f"⚠ {site['id']}: topicsQueueが空です。site.jsonにトピックを補充してください")
        return

    for _ in range(min(n, len(queue))):
        topic = queue.pop(0)
        print(f"→ {site['id']}: 「{topic}」を生成中...")
        raw = call_claude(ARTICLE_PROMPT.format(
            niche=site["niche"], title=site["title"],
            audience=site["audience"], topic=topic,
        ))
        article = parse_json(raw)
        slug = re.sub(r"[^a-z0-9-]", "", article["slug"].lower()) or "article"
        image_name = generate_eyecatch(site_dir, slug, article.get("image_prompt"))
        path = write_article(site_dir, article, image_name)
        site.setdefault("topicsDone", []).append(topic)
        print(f"  ✓ 保存: {path.relative_to(ROOT)}")

    site["topicsQueue"] = queue
    site_file.write_text(json.dumps(site, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else None
    site_dirs = [d for d in sorted(SITES_DIR.iterdir()) if (d / "site.json").exists()]
    if target:
        site_dirs = [d for d in site_dirs if d.name == target]
        if not site_dirs:
            sys.exit(f"サイトが見つかりません: {target}")
    for d in site_dirs:
        generate_for_site(d)


if __name__ == "__main__":
    main()
