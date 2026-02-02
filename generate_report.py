#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hacker News Daily Report Generator
Fetches top 5 articles from Hacker News, generates a Japanese report using AI,
and posts it to Discord via webhook.
"""

import os
import sys
import re
import requests
from typing import List, Dict, Optional
from datetime import datetime
from openai import OpenAI


class HackerNewsAPI:
    """Fetches data from Hacker News API"""
    
    BASE_URL = "https://hacker-news.firebaseio.com/v0"
    
    def get_top_stories(self, limit: int = 5) -> List[Dict]:
        """Get top N stories from Hacker News"""
        try:
            # Get top story IDs
            response = requests.get(f"{self.BASE_URL}/topstories.json", timeout=10)
            response.raise_for_status()
            story_ids = response.json()[:limit]
            
            # Fetch details for each story
            stories = []
            for story_id in story_ids:
                story = self._get_item(story_id)
                if story:
                    stories.append(story)
            
            return stories
        except Exception as e:
            print(f"Error fetching top stories: {e}")
            return []
    
    def _get_item(self, item_id: int, depth: int = 0) -> Optional[Dict]:
        """Get item details by ID"""
        try:
            response = requests.get(f"{self.BASE_URL}/item/{item_id}.json", timeout=10)
            response.raise_for_status()
            item = response.json()
            
            # Get top comments for top-level stories only
            if (
                item
                and item.get('type') == 'story'
                and 'kids' in item
                and depth == 0
            ):
                item['top_comments'] = []
                # Get first 3 comments
                for comment_id in item['kids'][:3]:
                    comment = self._get_item(comment_id, depth + 1)
                    if comment and comment.get('text'):
                        item['top_comments'].append(comment)
            
            return item
        except Exception as e:
            print(f"Error fetching item {item_id}: {e}")
            return None


class ReportGenerator:
    """Generates report using OpenAI-compatible API"""
    
    def __init__(self, api_key: str, base_url: Optional[str] = None, model: Optional[str] = None):
        """Initialize OpenAI client with custom base URL if provided"""
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        
        self.client = OpenAI(**client_kwargs)
        # Use provided model, or get from env, or use default
        self.model = model or os.getenv("OPENAI_MODEL") or "gpt-3.5-turbo"
    
    def generate_report(self, stories: List[Dict]) -> str:
        """Generate Japanese report from Hacker News stories"""
        # Prepare context for AI
        context = self._prepare_context(stories)
        
        # Get current date in JST
        from datetime import timezone, timedelta
        jst = timezone(timedelta(hours=9))
        current_date = datetime.now(jst).strftime('%Y年%m月%d日')
        
        prompt = f"""あなたはテクノロジーニュースのレポーターです。
以下のHacker Newsのトップ5記事とコメントを元に、日本語で読みやすいレポートを作成してください。

記事データ:
{context}

以下の形式でレポートを作成してください:
1. タイトル: 「Hacker News デイリーレポート - {current_date}」
2. 簡単な導入文
3. 各記事について:
   - 記事タイトルとURL
   - 記事の要点（コメントも参考にして）
   - なぜ重要か、興味深い点
4. 全体的な傾向やまとめ

読みやすく、情報価値の高いレポートにしてください。"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "あなたは優秀なテクノロジーニュースのレポーターです。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=2000
            )
            
            return response.choices[0].message.content
        except Exception as e:
            print(f"Error generating report: {e}")
            raise
    
    def self_review_report(self, report: str) -> str:
        """AI self-reviews the generated report and returns improved version"""
        review_prompt = f"""以下のHacker Newsレポートをレビューして、改善してください。

レビュー観点:
1. 情報の正確性と完全性
2. 読みやすさと構成
3. 日本語の自然さ
4. 重要なポイントが明確か
5. 全体的な品質

レポート:
{report}

改善版のレポートを出力してください（レビューコメントは不要、改善されたレポートのみ出力）。"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "あなたは優秀な編集者です。レポートを改善してください。"},
                    {"role": "user", "content": review_prompt}
                ],
                temperature=0.5,
                max_tokens=2500
            )
            
            return response.choices[0].message.content
        except Exception as e:
            print(f"Error reviewing report: {e}")
            # Return original if review fails
            return report
    
    def _prepare_context(self, stories: List[Dict]) -> str:
        """Prepare formatted context from stories"""
        context_parts = []
        
        for i, story in enumerate(stories, 1):
            title = story.get('title', 'No title')
            url = story.get('url', '')
            # Fallback to HN discussion link if URL is missing (Ask HN/Show HN)
            if not url:
                url = f"https://news.ycombinator.com/item?id={story.get('id', '')}"
            score = story.get('score', 0)
            comments_count = story.get('descendants', 0)
            
            part = f"\n【記事 {i}】\n"
            part += f"タイトル: {title}\n"
            part += f"URL: {url}\n"
            part += f"スコア: {score} | コメント数: {comments_count}\n"
            
            # Add top comments if available
            if 'top_comments' in story and story['top_comments']:
                part += "主なコメント:\n"
                for j, comment in enumerate(story['top_comments'][:3], 1):
                    text = comment.get('text', '')
                    # Clean HTML tags from comment text
                    text = re.sub('<[^<]+?>', '', text)
                    text = text[:200] + '...' if len(text) > 200 else text
                    part += f"  - {text}\n"
            
            context_parts.append(part)
        
        return '\n'.join(context_parts)


class DiscordWebhook:
    """Posts messages to Discord via webhook"""
    
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
    
    def post_message(self, content: str) -> bool:
        """Post message to Discord"""
        try:
            # Discord has a 2000 character limit per message
            # Split if necessary
            if len(content) <= 2000:
                self._send_chunk(content)
            else:
                # Split into chunks
                chunks = self._split_content(content, 2000)
                for chunk in chunks:
                    self._send_chunk(chunk)
            
            return True
        except Exception as e:
            print(f"Error posting to Discord: {e}")
            return False
    
    def _send_chunk(self, content: str):
        """Send a single chunk to Discord"""
        payload = {
            "content": content,
            "allowed_mentions": {"parse": []}  # Disable all mention parsing
        }
        response = requests.post(
            self.webhook_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        response.raise_for_status()
    
    def _split_content(self, content: str, max_length: int) -> List[str]:
        """Split content into chunks respecting max_length"""
        chunks = []
        lines = content.split('\n')
        current_chunk = ""
        
        for line in lines:
            # If a single line is too long (or exactly at the limit), split it
            if len(line) >= max_length:
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = ""
                # Split long line into chunks
                for i in range(0, len(line), max_length):
                    chunks.append(line[i:i+max_length])
            elif len(current_chunk) + len(line) + 1 <= max_length:
                current_chunk += line + '\n'
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = line + '\n'
        
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks


def main():
    """Main execution function"""
    print("Starting Hacker News Daily Report Generator...")
    
    # Get configuration from environment variables
    github_token = os.getenv("GITHUB_TOKEN")
    openai_api_key = os.getenv("OPENAI_API_KEY")
    openai_base_url = os.getenv("OPENAI_BASE_URL")  # Optional
    openai_model = os.getenv("OPENAI_MODEL")  # Optional
    discord_webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    
    # Prioritize user-provided API key, fallback to GitHub Models
    if openai_api_key:
        print("Using configured OpenAI-compatible API...")
    elif github_token:
        print("Using GitHub Models for AI generation (no API key configured)...")
        openai_api_key = github_token
        # GitHub Models inference endpoint
        if not openai_base_url:
            openai_base_url = "https://models.inference.ai.azure.com"
        # Set default model for GitHub Models if not specified
        if not openai_model:
            openai_model = "gpt-4o-mini"
    else:
        # Neither API key nor GitHub token available
        print("Error: No API configuration found")
        print("  - Set OPENAI_API_KEY in secrets/environment, or")
        print("  - Run in GitHub Actions where GITHUB_TOKEN is automatically available")
        sys.exit(1)
    
    if not discord_webhook_url:
        print("Error: DISCORD_WEBHOOK_URL environment variable is required")
        sys.exit(1)
    
    try:
        # Step 1: Fetch top 5 stories from Hacker News
        print("Fetching top 5 stories from Hacker News...")
        hn_api = HackerNewsAPI()
        stories = hn_api.get_top_stories(limit=5)
        
        if not stories:
            print("Error: No stories fetched")
            sys.exit(1)
        
        print(f"Fetched {len(stories)} stories")
        
        # Step 2: Generate report using AI
        print("Generating report with AI...")
        generator = ReportGenerator(openai_api_key, openai_base_url, openai_model)
        report = generator.generate_report(stories)
        
        print("Initial report generated")
        
        # Step 3: Self-review the report
        print("Self-reviewing report with AI...")
        reviewed_report = generator.self_review_report(report)
        
        print("Report reviewed and improved")
        
        # Step 4: Post to Discord
        print("Posting report to Discord...")
        webhook = DiscordWebhook(discord_webhook_url)
        success = webhook.post_message(reviewed_report)
        
        if success:
            print("✓ Report successfully posted to Discord!")
            print("\n" + "="*50)
            print("FINAL REPORT:")
            print("="*50)
            print(reviewed_report)
            print("="*50)
        else:
            print("✗ Failed to post report to Discord")
            sys.exit(1)
            
    except Exception as e:
        print(f"Error in main execution: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
