"""楽天市場API(2026年新仕様)で商品を検索し、アフィリエイトリンク付きの商品情報を返す。

必要な認証情報(環境変数またはsite.jsonのaffiliate設定):
    RAKUTEN_APP_ID       アプリケーションID (Rakuten Developersで発行、UUID形式)
    RAKUTEN_AFFILIATE_ID 楽天アフィリエイトID
    RAKUTEN_ACCESS_KEY   アクセスキー(秘密情報。環境変数かGitHub Secretsで渡す。
                         ローカルでは data/rakuten.env に記入)

未設定の場合は None を返し、ビルド側が通常の検索リンクにフォールバックする。
"""
import json
import os
import time
import urllib.parse
import urllib.request

# 2026年新仕様: 旧 app.rakuten.co.jp/services は2026年5月に廃止
API_URL = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20220601"
CACHE_TTL_DAYS = 7
_last_call = 0.0


def _credentials(site):
    aff = site.get("affiliate", {})
    app_id = os.environ.get("RAKUTEN_APP_ID") or aff.get("rakutenAppId", "")
    aff_id = os.environ.get("RAKUTEN_AFFILIATE_ID") or aff.get("rakutenAffiliateId", "")
    access_key = os.environ.get("RAKUTEN_ACCESS_KEY") or aff.get("rakutenAccessKey", "")
    return app_id, aff_id, access_key


def resolve_product(keyword, site, cache):
    """キーワードで楽天市場を検索し、最上位商品の情報を返す(7日キャッシュ付き)"""
    app_id, aff_id, access_key = _credentials(site)
    if not app_id or not aff_id or not access_key:
        return None

    now = time.time()
    hit = cache.get(keyword)
    if hit and now - hit.get("fetchedAt", 0) < CACHE_TTL_DAYS * 86400:
        return hit["item"] or None

    global _last_call
    wait = 1.1 - (now - _last_call)  # レート制限(1リクエスト/秒)対策
    if wait > 0:
        time.sleep(wait)
    _last_call = time.time()

    params = urllib.parse.urlencode({
        "applicationId": app_id,
        "accessKey": access_key,
        "affiliateId": aff_id,
        "keyword": keyword,
        "hits": 1,
        "sort": "standard",
        "format": "json",
        "formatVersion": 2,
    })
    # 新APIは「許可されたウェブサイト」の検証のためReferer+Originヘッダーが必須
    origin = ""
    if site.get("url"):
        parts = urllib.parse.urlsplit(site["url"])
        origin = f"{parts.scheme}://{parts.netloc}"
    headers = {"Referer": origin + "/", "Origin": origin} if origin else {}
    try:
        req = urllib.request.Request(f"{API_URL}?{params}", headers=headers)
        with urllib.request.urlopen(req, timeout=15) as res:
            data = json.loads(res.read().decode("utf-8"))
        items = data.get("Items") or []
        if not items:
            item = None
        else:
            it = items[0]
            images = it.get("mediumImageUrls") or []
            # サムネイルはデフォルト128x128なので、URLパラメータで400x400に拡大する
            image_url = (images[0] or "").replace("_ex=128x128", "_ex=400x400") if images else ""
            item = {
                "name": it.get("itemName", ""),
                "price": it.get("itemPrice"),
                "affiliateUrl": it.get("affiliateUrl") or it.get("itemUrl"),
                "imageUrl": image_url,
            }
    except Exception as e:
        print(f"  ⚠ 楽天API失敗 ({keyword}): {e} — 検索リンクにフォールバックします")
        return hit["item"] if hit else None

    cache[keyword] = {"fetchedAt": time.time(), "item": item}
    return item
