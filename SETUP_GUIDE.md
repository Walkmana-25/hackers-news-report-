# セットアップガイド / Setup Guide

このガイドでは、Hacker News Daily Report Generatorの設定方法を説明します。

## 必要なもの

1. **Discord Webhook URL**（必須）
   - レポートを投稿するDiscordチャンネルのWebhook URL

2. **AIモデルの選択**（以下のいずれか）
   - **GitHub Models**（推奨・無料）：GitHub Actions実行時に自動的に使用されます
   - **OpenAI API**：https://platform.openai.com/
   - **その他のOpenAI互換API**：Azure OpenAI, ローカルLLMなど

## セットアップ手順

### 1. Discord Webhookの作成

1. Discordアプリケーションを開く
2. レポートを投稿したいチャンネルを選択
3. チャンネル名の横の⚙️（設定）をクリック
4. 「連携サービス」→「ウェブフック」をクリック
5. 「新しいウェブフック」をクリック
6. ウェブフックの名前を設定（例：「Hacker News Bot」）
7. 「ウェブフックURLをコピー」をクリック

### 2. GitHubシークレットの設定

1. GitHubでこのリポジトリを開く
2. **Settings** タブをクリック
3. 左サイドバーで **Secrets and variables** > **Actions** を選択
4. **New repository secret** をクリック
5. 以下のシークレットを追加：

#### 必須シークレット:

**DISCORD_WEBHOOK_URL**
- Name: `DISCORD_WEBHOOK_URL`
- Secret: ステップ1で取得したWebhook URL

#### AIモデルの設定:

**方法A: GitHub Models を使用（推奨・無料）**

GitHub Actions実行時は自動的に`GITHUB_TOKEN`を使用してGitHub Modelsにアクセスします。
追加のシークレット設定は不要です。

- デフォルトモデル: `gpt-4o-mini`
- モデルを変更する場合は、以下のオプションシークレットを設定してください

**方法B: OpenAI または互換APIを使用**

以下のシークレットを設定してください：

**OPENAI_API_KEY**
- Name: `OPENAI_API_KEY`
- Secret: あなたのOpenAI APIキー（または互換APIのキー）

#### オプションシークレット:

**OPENAI_BASE_URL**（OpenAI以外のAPIを使用する場合）
- Name: `OPENAI_BASE_URL`
- Secret: APIのベースURL（例：`https://api.openai.com/v1`）

**OPENAI_MODEL**（デフォルト以外のモデルを使用する場合）
- Name: `OPENAI_MODEL`
- Secret: モデル名
  - GitHub Models使用時: `gpt-4o`, `gpt-4o-mini`, `gpt-4-turbo`など
  - OpenAI使用時: `gpt-4`, `gpt-3.5-turbo`など

### 3. 動作確認

設定完了後、手動で実行してテストできます：

1. リポジトリの **Actions** タブを開く
2. 左サイドバーで **Daily Hacker News Report** を選択
3. **Run workflow** ボタンをクリック
4. **Run workflow** を再度クリックして実行開始
5. 実行が完了したら、Discordチャンネルでレポートを確認

### 4. 自動実行の確認

設定が完了すると、以下のスケジュールで自動実行されます：
- **毎日午前9時（日本時間）** = 午前0時（UTC）

次回の実行時刻は、Actions タブの該当ワークフローで確認できます。

## トラブルシューティング

### レポートが投稿されない

1. **Actionsタブでエラーを確認**
   - Actions > Daily Hacker News Report > 最新の実行
   - エラーログを確認

2. **シークレットの確認**
   - Settings > Secrets and variables > Actions
   - すべての必須シークレットが設定されているか確認

3. **Discord Webhook URLの確認**
   - URLが正しいか確認
   - Webhookが削除されていないか確認

### APIエラーが発生する

1. **OpenAI APIキーの確認**
   - キーが有効か確認
   - API使用量が制限に達していないか確認

2. **モデル名の確認**
   - 指定したモデルが利用可能か確認
   - デフォルト（gpt-3.5-turbo）を試す

## カスタマイズ

### 記事の数を変更

`generate_report.py` 内の、トップストーリーを取得している箇所：
```python
stories = hn_api.get_top_stories(limit=5)  # 5を希望の数に変更
```

### 実行時刻を変更

`.github/workflows/daily_report.yml` の6行目：
```yaml
- cron: '0 0 * * *'  # UTC時間で指定
```

日本時間の9時 = UTC 0時なので、他の時刻にしたい場合は調整してください。
例：
- 日本時間12時 = UTC 3時 → `'0 3 * * *'`
- 日本時間18時 = UTC 9時 → `'0 9 * * *'`

### レポートの形式を変更

`generate_report.py` の `generate_report()` メソッド内のプロンプトを編集してください。

## サポート

問題が解決しない場合は、Issueを作成してください。
