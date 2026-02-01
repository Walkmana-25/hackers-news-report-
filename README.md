# Hacker News Daily Report Generator

毎朝自動的にHacker Newsのトップ5記事を取得し、AIで日本語レポートを生成してDiscordに投稿するシステムです。

## 機能

- 🌐 Hacker News APIから毎日トップ5記事を取得
- 💬 記事のコメントも取得して分析
- 🤖 OpenAI互換APIを使用して日本語レポートを生成
- ✅ AIによるレポートのセルフレビュー機能
- 📨 Discordウェブフックで自動投稿
- ⏰ GitHub Actionsで毎朝自動実行

## セットアップ

### 1. リポジトリのシークレット設定

GitHub リポジトリの Settings > Secrets and variables > Actions で以下のシークレットを設定してください：

#### 必須設定:
- `DISCORD_WEBHOOK_URL`: Discord ウェブフックURL

#### AI モデルの設定（以下のいずれか）:

**オプション A: GitHub Models を使用（推奨・無料）**
- GitHub Actions実行時は自動的に`GITHUB_TOKEN`を使用してGitHub Modelsにアクセスします
- 追加のシークレット設定は不要です
- デフォルトモデル: `gpt-4o-mini`
- モデルを変更したい場合は、`OPENAI_MODEL`シークレットを設定してください（例: `gpt-4o`, `gpt-4-turbo`など）

**オプション B: OpenAI または互換APIを使用**
- `OPENAI_API_KEY`: OpenAI APIキー（または互換APIのキー）
- `OPENAI_BASE_URL`: OpenAI互換APIのベースURL（例: `https://api.openai.com/v1`）
- `OPENAI_MODEL`: 使用するモデル名（デフォルト: `gpt-3.5-turbo`）

### 2. Discord ウェブフックの取得方法

1. Discordで投稿先のチャンネルを開く
2. チャンネル設定 > 連携サービス > ウェブフック
3. 「新しいウェブフック」をクリック
4. ウェブフックURLをコピーして、GitHubシークレットに設定

### 3. 実行スケジュール

GitHub Actionsは毎日午前9時（JST）に自動実行されます。  
手動で実行する場合は、Actions タブから「Daily Hacker News Report」ワークフローを選択し、「Run workflow」をクリックしてください。

## ローカルでの実行

### 必要な環境

- Python 3.11以上
- pip

### インストール

```bash
# 依存パッケージのインストール
pip install -r requirements.txt
```

### 環境変数の設定

```bash
# 必須
export OPENAI_API_KEY="your-api-key"
export DISCORD_WEBHOOK_URL="your-webhook-url"

# オプション
export OPENAI_BASE_URL="https://api.openai.com/v1"
export OPENAI_MODEL="gpt-3.5-turbo"
```

### 実行

```bash
python generate_report.py
```

## 技術スタック

- **Python 3.11**: メインプログラミング言語
- **Hacker News API**: 記事データの取得
- **OpenAI API**: レポート生成とレビュー
- **Discord Webhook**: レポートの投稿
- **GitHub Actions**: 自動実行

## ファイル構成

```
.
├── .github/
│   └── workflows/
│       └── daily_report.yml    # GitHub Actionsワークフロー
├── generate_report.py          # メインスクリプト
├── requirements.txt            # Python依存パッケージ
├── .gitignore                  # Git除外設定
└── README.md                   # このファイル
```

## プログラムの流れ

1. **記事取得**: Hacker News APIからトップ5記事と各記事の上位3コメントを取得
2. **レポート生成**: OpenAI互換APIを使用して、記事とコメントを元に日本語レポートを生成
3. **セルフレビュー**: AIが生成したレポートを自己レビューして改善
4. **Discord投稿**: 最終レポートをDiscordウェブフック経由で投稿

## カスタマイズ

### 記事数の変更

`generate_report.py`の`main()`関数内で記事数を変更できます：

```python
stories = hn_api.get_top_stories(limit=5)  # 5を変更
```

### レポート形式の変更

`ReportGenerator`クラスの`generate_report()`メソッド内のプロンプトを編集してください。

## ライセンス

MIT License

## 貢献

Issue や Pull Request を歓迎します！