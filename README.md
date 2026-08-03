# niche-affiliate — ニッチアフィリエイトサイト量産エンジン

Markdownの記事から複数のアフィリエイトサイトを自動ビルドし、GitHub Pagesで無料公開する仕組みです。
毎週月曜の朝、Claude APIが新記事を1本自動生成して公開します。

## 構成

```
engine/
  build.py      # 静的サイトビルダー(sites/ → dist/)
  generate.py   # Claude APIで週次記事を自動生成
  rakuten.py    # 楽天APIで商品情報+アフィリエイトリンクを取得
sites/
  hedgehog-degu/          # サイト1: ハリネズミ・デグー用品
    site.json             # サイト設定(テーマ色・トピックキュー・アフィリエイトID)
    content/*.md          # 記事(frontmatter + Markdown)
.github/workflows/publish.yml  # 週次自動実行(生成→ビルド→デプロイ)
```

## ローカルでの使い方

```bash
# 全サイトをビルド(dist/ に出力)
python3 engine/build.py

# プレビュー(http://localhost:8000)
python3 -m http.server 8000 -d dist

# 記事を1本手動生成(APIキーが必要)
ANTHROPIC_API_KEY=sk-... python3 engine/generate.py hedgehog-degu
```

依存ライブラリ: `pip3 install markdown pyyaml`

## 公開までの手順

### 1. GitHubリポジトリを作成してpush

```bash
cd niche-affiliate
git init && git add -A && git commit -m "initial commit"
gh repo create niche-affiliate --public --source=. --push
```

### 2. GitHub Pagesを有効化

リポジトリの **Settings → Pages → Source** を **GitHub Actions** に変更。
以後、mainにpushするたび自動デプロイされます。
公開URLは `https://<ユーザー名>.github.io/niche-affiliate/hedgehog-degu/` です。
決まったら `sites/hedgehog-degu/site.json` の `url` に設定してください(サイトマップ・canonicalに使われます)。

### 3. Secretsを登録(Settings → Secrets and variables → Actions)

| Secret名 | 内容 | 取得先 |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude APIキー(週次記事生成に必須) | https://console.anthropic.com/ |
| `GEMINI_API_KEY` | Gemini APIキー(記事アイキャッチの自動生成。任意) | https://aistudio.google.com/ |
| `RAKUTEN_APP_ID` | 楽天のアプリケーションID(UUID形式) | https://webservice.rakuten.co.jp/ |
| `RAKUTEN_ACCESS_KEY` | 楽天のアクセスキー(秘密情報。2026年新API仕様で必須) | 同上の管理画面 |
| `RAKUTEN_AFFILIATE_ID` | 楽天アフィリエイトID | https://affiliate.rakuten.co.jp/ |
| `AMAZON_TAG` | Amazonアソシエイトのトラッキングタグ | https://affiliate.amazon.co.jp/ |

- 楽天の2つが未設定の間は、商品リンクは通常の検索リンク(報酬なし)になります
- Amazonアソシエイトは審査制(180日以内に3件の成果が必要)。サイトが育ってからの申請でOK
- **アカウント登録・審査対応はすべてご自身で行ってください**

### 4. 週次自動運転

`.github/workflows/publish.yml` が毎週月曜6:00(JST)に実行され、

1. `site.json` の `topicsQueue` 先頭のトピックで記事を生成
2. リポジトリにコミット
3. サイトを再ビルドしてデプロイ

します。Actionsタブから `workflow_dispatch` で手動実行も可能です。

## 2サイト目以降の追加方法

1. `sites/hedgehog-degu` をコピーして `sites/<新サイトID>` を作成
2. `site.json` の `id`・タイトル・ニッチ・テーマ色・`topicsQueue` を書き換え
3. `content/` の記事を差し替え(最初の数本はClaude Codeと一緒に書くのがおすすめ)
4. pushすれば `https://<ユーザー名>.github.io/niche-affiliate/<新サイトID>/` に公開される

## 運用コストの目安

- ホスティング: 無料(GitHub Pages)
- 記事生成: 週1本あたり数円〜十数円程度(Claude API)
- 独自ドメイン(任意): 年1,000〜2,000円程度

## ⚠️ 運用上の注意

- **副業規定**: 勤務先の副業ポリシーを事前に確認すること
- **ステマ規制(景品表示法)**: 全ページにPR表記を自動挿入済み。消さないこと
- **Googleのスパムポリシー**: 検索順位目的の低品質な大量生成はペナルティ対象。
  週1本ペースを守り、生成された記事は公開前に目を通して事実誤認を直すこと(特にペットの健康情報)
- **収益の期待値**: この種のサイトの多くは収益ゼロ〜月数百円からのスタート。
  数ヶ月単位で育てる前提で運用すること
