#!/usr/bin/env python3
"""静的サイトビルダー: sites/*/ の記事(Markdown)を dist/ にHTMLとして出力する。

使い方:
    python3 engine/build.py            # 全サイトをビルド
    python3 engine/build.py <site_id>  # 特定サイトのみビルド
"""
import html
import json
import os
import shutil
import sys
import urllib.parse
from datetime import date
from pathlib import Path

import markdown
import yaml

sys.path.insert(0, str(Path(__file__).parent))
from rakuten import resolve_product  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SITES_DIR = ROOT / "sites"
DIST = ROOT / "dist"

MD_EXTENSIONS = ["tables", "sane_lists"]


def esc(s):
    return html.escape(str(s), quote=True)


def load_article(md_path: Path):
    text = md_path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError(f"frontmatterがありません: {md_path}")
    _, fm, body = text.split("---", 2)
    meta = yaml.safe_load(fm)
    meta["slug"] = meta.get("slug") or md_path.stem
    meta["body"] = body.strip()
    return meta


def product_card(product, resolved, amazon_tag):
    """商品カードHTML。resolved は楽天APIの結果(なければ検索リンクにフォールバック)"""
    name = product["name"]
    keyword = product["keyword"]
    note = product.get("note", "")

    rakuten_q = urllib.parse.quote(keyword)
    amazon_q = urllib.parse.quote_plus(keyword)
    amazon_url = f"https://www.amazon.co.jp/s?k={amazon_q}"
    if amazon_tag:
        amazon_url += f"&tag={urllib.parse.quote(amazon_tag)}"

    if resolved:
        rakuten_url = resolved["affiliateUrl"]
        img = (
            f'<img class="product-img" src="{esc(resolved["imageUrl"])}" alt="{esc(name)}" loading="lazy">'
            if resolved.get("imageUrl")
            else ""
        )
        price = (
            f'<p class="product-price">楽天参考価格: {int(resolved["price"]):,}円</p>'
            if resolved.get("price")
            else ""
        )
    else:
        rakuten_url = f"https://search.rakuten.co.jp/search/mall/{rakuten_q}/"
        img = ""
        price = ""

    note_html = f'<p class="product-note">{esc(note)}</p>' if note else ""
    return f'''
<div class="product-card">
{img}
<div class="product-body">
<p class="product-name">{esc(name)}</p>
{note_html}
{price}
<div class="product-links">
<a class="btn btn-rakuten" href="{esc(rakuten_url)}" target="_blank" rel="sponsored nofollow noopener">楽天市場で見る</a>
<a class="btn btn-amazon" href="{esc(amazon_url)}" target="_blank" rel="sponsored nofollow noopener">Amazonで探す</a>
</div>
</div>
</div>
'''


def render_body(article, site, cache):
    body = article["body"]
    products = article.get("products") or []
    amazon_tag = os.environ.get("AMAZON_TAG") or site["affiliate"].get("amazonTag", "")
    for i, product in enumerate(products, start=1):
        resolved = resolve_product(product["keyword"], site, cache)
        body = body.replace("{{product:%d}}" % i, product_card(product, resolved, amazon_tag))
    return markdown.markdown(body, extensions=MD_EXTENSIONS)


def layout(site, *, title, description, content, rel, canonical=None, noindex=False, og_image=None):
    t = site["theme"]
    year = date.today().year
    canonical_tag = f'<link rel="canonical" href="{esc(canonical)}">' if canonical else ""
    robots = '<meta name="robots" content="noindex">' if noindex else ""
    og_tags = ""
    if og_image and site.get("url"):
        og_abs = site["url"].rstrip("/") + "/" + og_image.lstrip("/")
        og_tags = (f'<meta property="og:title" content="{esc(title)}">'
                   f'<meta property="og:image" content="{esc(og_abs)}">'
                   f'<meta name="twitter:card" content="summary_large_image">')
    verification = ""
    if site.get("googleSiteVerification"):
        verification = f'<meta name="google-site-verification" content="{esc(site["googleSiteVerification"])}">'
    header_cls = "site-header"
    header_style = ""
    if site.get("_headerImage"):
        header_cls += " site-header--photo"
        header_style = (f' style="background-image: linear-gradient(rgba(48,33,18,.35), rgba(48,33,18,.55)),'
                        f' url({rel}assets/{site["_headerImage"]});"')
    return f'''<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
{canonical_tag}
{robots}
{og_tags}
{verification}
<link rel="stylesheet" href="{rel}style.css">
<style>:root {{ --primary: {t["primary"]}; --accent: {t["accent"]}; --bg: {t["bg"]}; }}</style>
</head>
<body>
<header class="{header_cls}"{header_style}>
<a class="site-title" href="{rel}index.html">{esc(site["title"])}</a>
<p class="site-tagline">{esc(site["tagline"])}</p>
</header>
<main class="container">
{content}
</main>
<footer class="site-footer">
<nav>
<a href="{rel}about.html">運営者情報・免責事項</a> ／
<a href="{rel}privacy.html">プライバシーポリシー</a>
</nav>
<p>&copy; {year} {esc(site["title"])}</p>
</footer>
</body>
</html>
'''


PR_NOTE = '<p class="pr-note">※本記事にはアフィリエイト広告(プロモーション)が含まれています。</p>'


def article_page(site, article, body_html, all_articles):
    related = [a for a in all_articles
               if a["slug"] != article["slug"] and a.get("category") == article.get("category")][:3]
    related_html = ""
    if related:
        items = "".join(
            f'<li><a href="{esc(a["slug"])}.html">{esc(a["title"])}</a></li>' for a in related
        )
        related_html = f'<section class="related"><h2>関連記事</h2><ul>{items}</ul></section>'

    eyecatch = ""
    if article.get("image"):
        eyecatch = f'<img class="eyecatch" src="../assets/{esc(article["image"])}" alt="{esc(article["title"])}">'
    content = f'''
<article>
{PR_NOTE}
<p class="meta"><span class="category">{esc(article.get("category", ""))}</span> ・ {esc(article["date"])}</p>
<h1>{esc(article["title"])}</h1>
{eyecatch}
{body_html}
<p class="disclaimer">※飼育環境や個体によって適した用品・世話の仕方は異なります。体調に関わる判断は必ず獣医師にご相談ください。掲載価格・仕様は執筆時点の情報です。</p>
</article>
{related_html}
'''
    canonical = None
    if site.get("url"):
        canonical = site["url"].rstrip("/") + f"/articles/{article['slug']}.html"
    og_image = f'assets/{article["image"]}' if article.get("image") else None
    return layout(site, title=f'{article["title"]} | {site["title"]}',
                  description=article.get("description", ""),
                  content=content, rel="../", canonical=canonical, og_image=og_image)


def index_page(site, articles):
    cards = ""
    for a in articles:
        thumb = ""
        if a.get("image"):
            thumb = f'<img class="card-thumb" src="assets/{esc(a["image"])}" alt="" loading="lazy">'
        cards += f'''
<a class="card" href="articles/{esc(a["slug"])}.html">
{thumb}
<div class="card-body">
<p class="meta"><span class="category">{esc(a.get("category", ""))}</span> ・ {esc(a["date"])}</p>
<h2>{esc(a["title"])}</h2>
<p>{esc(a.get("description", ""))}</p>
</div>
</a>
'''
    content = f'''
<section class="hero">
<h1>{esc(site["title"])}</h1>
<p>{esc(site["description"])}</p>
</section>
{PR_NOTE}
<section class="card-list">
{cards}
</section>
'''
    return layout(site, title=site["title"], description=site["description"],
                  content=content, rel="", canonical=site.get("url") or None)


def about_page(site):
    author = site.get("author", "管理人")
    content = f'''
<article>
<h1>運営者情報・免責事項</h1>
<h2>このサイトについて</h2>
<p>「{esc(site["title"])}」は、{esc(site["niche"])}に関する情報と用品の選び方を紹介する個人運営のサイトです。</p>
<h2>運営者</h2>
<p>{esc(author)}</p>
<h2>広告について</h2>
<p>当サイトは、楽天アフィリエイトおよびAmazonアソシエイト・プログラムに参加しており、記事内のリンクを経由して商品が購入された場合に紹介料を受け取ることがあります。Amazonのアソシエイトとして、当サイトは適格販売により収入を得ています。広告が含まれる記事にはその旨を明記しています。</p>
<h2>免責事項</h2>
<p>掲載内容は執筆時点の一般的な情報に基づいており、正確性・完全性を保証するものではありません。価格・仕様は変動するため、購入前に必ずリンク先の最新情報をご確認ください。動物の健康に関わる判断は、獣医師にご相談ください。当サイトの情報の利用によって生じた損害について、運営者は責任を負いかねます。</p>
</article>
'''
    return layout(site, title=f'運営者情報・免責事項 | {site["title"]}',
                  description="運営者情報と免責事項", content=content, rel="")


def privacy_page(site):
    content = f'''
<article>
<h1>プライバシーポリシー</h1>
<h2>アフィリエイトプログラムについて</h2>
<p>当サイトは、楽天アフィリエイト、Amazonアソシエイト・プログラムその他のアフィリエイトプログラムに参加しています。リンク先の事業者は、購入履歴の計測のためCookieを使用することがあります。</p>
<h2>アクセス解析について</h2>
<p>当サイトでは、サイト改善のためにアクセス解析ツールを利用する場合があります。解析ツールはトラフィックデータ収集のためにCookieを使用することがありますが、このデータで個人を特定することはできません。</p>
<h2>お問い合わせ</h2>
<p>当サイトに関するお問い合わせは、運営者情報ページに記載の方法でご連絡ください。</p>
</article>
'''
    return layout(site, title=f'プライバシーポリシー | {site["title"]}',
                  description="プライバシーポリシー", content=content, rel="")


STYLE = '''
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: "Hiragino Sans", "Yu Gothic", sans-serif; background: var(--bg); color: #333; line-height: 1.9; }
.site-header { background: var(--primary); color: #fff; padding: 28px 20px; text-align: center; }
.site-header--photo { background-size: cover; background-position: center 42%; padding: 96px 20px; text-shadow: 0 1px 10px rgba(0,0,0,.55); }
.site-title { color: #fff; text-decoration: none; font-size: 1.6rem; font-weight: bold; }
.site-header--photo .site-title { font-size: 2rem; }
.site-tagline { font-size: .85rem; opacity: .92; margin-top: 6px; }
.container { max-width: 760px; margin: 0 auto; padding: 32px 20px 64px; }
.hero { text-align: center; padding: 16px 0 24px; }
.hero h1 { font-size: 1.5rem; color: var(--primary); }
.hero p { margin-top: 8px; color: #666; font-size: .95rem; }
.pr-note { font-size: .78rem; color: #888; background: #fff; border: 1px solid #e5ddd2; border-radius: 6px; padding: 6px 12px; margin: 12px 0 20px; }
.card-list { display: grid; gap: 20px; grid-template-columns: repeat(2, 1fr); }
@media (max-width: 640px) { .card-list { grid-template-columns: 1fr; } }
.card { display: block; background: #fff; border: 1px solid #e5ddd2; border-radius: 12px; overflow: hidden; text-decoration: none; color: inherit; transition: box-shadow .15s, transform .15s; }
.card:hover { box-shadow: 0 6px 18px rgba(0,0,0,.1); transform: translateY(-2px); }
.card-thumb { display: block; width: 100%; aspect-ratio: 16/9; object-fit: cover; }
.card-body { padding: 16px 18px 18px; }
.card h2 { font-size: 1.05rem; color: var(--primary); margin: 6px 0; line-height: 1.5; }
.card p { font-size: .88rem; color: #666; }
.eyecatch { width: 100%; border-radius: 10px; margin: 4px 0 18px; display: block; }
.meta { font-size: .8rem; color: #999; }
.category { background: var(--accent); color: #fff; border-radius: 4px; padding: 1px 8px; font-size: .75rem; }
article { background: #fff; border: 1px solid #e5ddd2; border-radius: 10px; padding: 32px 28px; }
article h1 { font-size: 1.5rem; color: var(--primary); margin: 10px 0 20px; line-height: 1.5; }
article h2 { font-size: 1.2rem; color: var(--primary); border-left: 4px solid var(--accent); padding-left: 10px; margin: 36px 0 14px; }
article h3 { font-size: 1.05rem; margin: 24px 0 10px; }
article p { margin: 12px 0; }
article ul, article ol { margin: 12px 0 12px 24px; }
article table { border-collapse: collapse; width: 100%; margin: 16px 0; font-size: .9rem; }
article th, article td { border: 1px solid #ddd; padding: 8px 10px; text-align: left; }
article th { background: var(--bg); }
.product-card { display: flex; gap: 16px; background: var(--bg); border: 1px solid #e0d5c5; border-radius: 10px; padding: 18px; margin: 20px 0; }
.product-img { width: 110px; height: 110px; object-fit: contain; background: #fff; border-radius: 8px; flex-shrink: 0; }
.product-name { font-weight: bold; margin: 0 0 6px; }
.product-note { font-size: .85rem; color: #666; margin: 0 0 6px; }
.product-price { font-size: .9rem; color: #c0392b; font-weight: bold; margin: 0 0 10px; }
.product-links { display: flex; gap: 10px; flex-wrap: wrap; }
.btn { display: inline-block; padding: 8px 18px; border-radius: 6px; color: #fff; text-decoration: none; font-size: .88rem; font-weight: bold; }
.btn-rakuten { background: #bf0000; }
.btn-amazon { background: #ff9900; }
.btn:hover { opacity: .85; }
.disclaimer { font-size: .78rem; color: #999; border-top: 1px solid #eee; padding-top: 14px; margin-top: 32px; }
.related { margin-top: 28px; background: #fff; border: 1px solid #e5ddd2; border-radius: 10px; padding: 20px 28px; }
.related h2 { font-size: 1rem; color: var(--primary); margin-bottom: 8px; }
.related ul { margin-left: 22px; }
.site-footer { text-align: center; padding: 28px 20px; font-size: .8rem; color: #888; }
.site-footer a { color: #888; }
@media (max-width: 520px) { .product-card { flex-direction: column; } .product-img { width: 90px; height: 90px; } }
'''


def sitemap(site, articles):
    if not site.get("url"):
        return None
    base = site["url"].rstrip("/")
    urls = [f"{base}/index.html"] + [f"{base}/articles/{a['slug']}.html" for a in articles]
    entries = "".join(f"<url><loc>{esc(u)}</loc></url>" for u in urls)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{entries}</urlset>'


def build_site(site_dir: Path, cache: dict):
    site = json.loads((site_dir / "site.json").read_text(encoding="utf-8"))
    out = DIST / site["id"]
    (out / "articles").mkdir(parents=True, exist_ok=True)

    assets_dir = site_dir / "assets"
    if assets_dir.is_dir():
        shutil.copytree(assets_dir, out / "assets", dirs_exist_ok=True)
        for name in ("header.jpg", "header.png", "header.webp"):
            if (assets_dir / name).exists():
                site["_headerImage"] = name
                break

    articles = sorted(
        (load_article(p) for p in sorted((site_dir / "content").glob("*.md"))),
        key=lambda a: str(a["date"]), reverse=True,
    )
    for a in articles:
        a["date"] = str(a["date"])

    for a in articles:
        body_html = render_body(a, site, cache)
        (out / "articles" / f"{a['slug']}.html").write_text(
            article_page(site, a, body_html, articles), encoding="utf-8")

    (out / "index.html").write_text(index_page(site, articles), encoding="utf-8")
    (out / "about.html").write_text(about_page(site), encoding="utf-8")
    (out / "privacy.html").write_text(privacy_page(site), encoding="utf-8")
    (out / "style.css").write_text(STYLE, encoding="utf-8")
    sm = sitemap(site, articles)
    if sm:
        (out / "sitemap.xml").write_text(sm, encoding="utf-8")
    print(f"✓ {site['id']}: 記事{len(articles)}本をビルドしました → {out}")
    return site


def load_local_env():
    """ローカル用の認証情報ファイル(git管理外)を環境変数に読み込む"""
    env_file = ROOT / "data" / "rakuten.env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def main():
    load_local_env()
    target = sys.argv[1] if len(sys.argv) > 1 else None
    cache_file = ROOT / "data" / "product_cache.json"
    cache = json.loads(cache_file.read_text(encoding="utf-8")) if cache_file.exists() else {}

    site_dirs = [d for d in sorted(SITES_DIR.iterdir()) if (d / "site.json").exists()]
    if target:
        site_dirs = [d for d in site_dirs if d.name == target]
        if not site_dirs:
            sys.exit(f"サイトが見つかりません: {target}")

    built = [build_site(d, cache) for d in site_dirs]

    # dist直下: サイト一覧(検索エンジンには載せない)
    links = "".join(f'<li><a href="{s["id"]}/index.html">{esc(s["title"])}</a></li>' for s in built)
    (DIST / "index.html").write_text(
        f'<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8">'
        f'<meta name="robots" content="noindex"><title>sites</title></head>'
        f'<body><ul>{links}</ul></body></html>', encoding="utf-8")

    cache_file.parent.mkdir(exist_ok=True)
    cache_file.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
