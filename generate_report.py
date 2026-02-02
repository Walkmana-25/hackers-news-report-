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
import html
import logging
import requests
from typing import List, Dict, Optional
from datetime import datetime, timezone, timedelta
from openai import OpenAI

MIN_SUMMARY_LENGTH = 50


logger = logging.getLogger(__name__)


class HackerNewsAPI:
    """Fetches data from Hacker News API"""
    
    BASE_URL = "https://hacker-news.firebaseio.com/v0"
    
    def get_top_stories(self, limit: int = 5) -> List[Dict]:
        """Get top N stories from Hacker News"""
        try:
            # Get top story IDs
            response = requests.get(f"{self.BASE_URL}/topstories.json", timeout=10)
            response.raise_for_status()
            story_ids = response.json()
            logger.info("Fetched %d top story IDs. Targeting first %d.", len(story_ids), limit)
            
            # Fetch details for each story until we collect the desired limit
            stories = []
            for story_id in story_ids:
                story = self._get_item(story_id)
                if story:
                    stories.append(story)
                    logger.info(
                        "Collected story %d/%d: %s",
                        len(stories),
                        limit,
                        story.get('title', 'No title')
                    )
                else:
                    logger.warning("Skipping story ID %s due to fetch error or missing data.", story_id)
                
                if len(stories) >= limit:
                    break
            
            return stories
        except Exception as e:
            logger.exception("Error fetching top stories: %s", e)
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
    
    def generate_story_summary(self, story: Dict, index: int) -> str:
        """Generate summary for a single story"""
        title = story.get("title", "No title")
        url = story.get("url") or f"https://news.ycombinator.com/item?id={story.get('id', '')}"
        score = story.get("score", 0)
        comments = story.get("top_comments", [])
        
        # Prepare comments text
        comments_text = []
        for c in comments:
            text = c.get("text", "")
            text = re.sub("<[^<]+?>", "", text)
            text = html.unescape(text)
            text = text[:200] + "..." if len(text) > 200 else text
            if text.strip():
                comments_text.append(text)
        comments_joined = "\n".join(f"- {t}" for t in comments_text) if comments_text else "コメントなし"
        
        prompt = f"""Hacker Newsのトップ記事 {index} を要約してください。
タイトル: {title}
URL: {url}
スコア: {score}
主なコメント:
{comments_joined}

以下の形式で短い日本語メッセージを作成してください:
- タイトルとURL
- 記事本文の推測要約（リンク先の概要として簡潔に）
- コメントから読み取れるポイントの要約
- なぜ重要か/興味深いかを一文
"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "あなたはテクノロジーニュースのライターです。簡潔にまとめてください。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.6,
                max_tokens=600
            )
            content = response.choices[0].message.content
            if isinstance(content, list):
                # Some providers return list of content blocks
                content = "".join(
                    block.get("text", "") if isinstance(block, dict) else str(block)
                    for block in content
                )

            if not content or not content.strip():
                logger.warning("Empty summary returned for story %d; using fallback text.", index)
                content = (
                    f"{title} ({url}) の要約を生成できませんでした。"
                    f" スコア: {score}。主要コメント: {comments_joined}"
                )
            return content
        except Exception as e:
            logger.exception("Error generating story summary: %s", e)
            return f"{title} ({url}) の要約生成に失敗しました。"

    def generate_overall_summary(self, story_messages: List[str]) -> str:
        """Generate overall summary from per-story messages"""
        joined = "\n\n".join(story_messages)
        count = len(story_messages)
        if count == 1:
            lead_text = "以下の記事要約を元に、全体の傾向とまとめを短く作成してください。日本語で200文字程度でお願いします。"
        else:
            lead_text = f"以下の{count}件の記事要約を元に、全体の傾向とまとめを短く作成してください。日本語で200文字程度でお願いします。"
        prompt = f"""{lead_text}

{joined}
"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "あなたはテクノロジーニュース編集者です。全体のまとめを作成してください。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5,
                max_tokens=400
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.exception("Error generating overall summary: %s", e)
            return "全体まとめの生成に失敗しました。"
    
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
                chunks = [content]
            else:
                chunks = self._split_content(content, 2000)
            
            logger.info("Posting report to Discord in %d message(s).", len(chunks))
            for idx, chunk in enumerate(chunks, 1):
                logger.info("Sending chunk %d/%d (length: %d)...", idx, len(chunks), len(chunk))
                self._send_chunk(chunk)
            
            return True
        except Exception as e:
            logger.exception("Error posting to Discord: %s", e)
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
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger.info("Starting Hacker News Daily Report Generator...")
    
    # Get configuration from environment variables
    github_token = os.getenv("GITHUB_TOKEN")
    openai_api_key = os.getenv("OPENAI_API_KEY")
    openai_base_url = os.getenv("OPENAI_BASE_URL")  # Optional
    openai_model = os.getenv("OPENAI_MODEL")  # Optional
    discord_webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    
    # Prioritize user-provided API key, fallback to GitHub Models
    if openai_api_key:
        logger.info("Using configured OpenAI-compatible API...")
    elif github_token:
        logger.info("Using GitHub Models for AI generation (no API key configured)...")
        openai_api_key = github_token
        # GitHub Models inference endpoint
        if not openai_base_url:
            openai_base_url = "https://models.inference.ai.azure.com"
        # Set default model for GitHub Models if not specified
        if not openai_model:
            openai_model = "gpt-4o-mini"
    else:
        # Neither API key nor GitHub token available
        logger.error("Error: No API configuration found")
        logger.error("  - Set OPENAI_API_KEY in secrets/environment, or")
        logger.error("  - Run in GitHub Actions where GITHUB_TOKEN is automatically available")
        sys.exit(1)
    
    if not discord_webhook_url:
        logger.error("Error: DISCORD_WEBHOOK_URL environment variable is required")
        sys.exit(1)
    
    try:
        # Step 1: Fetch top 5 stories from Hacker News
        logger.info("Fetching top 5 stories from Hacker News...")
        hn_api = HackerNewsAPI()
        stories = hn_api.get_top_stories(limit=5)
        
        if not stories:
            logger.error("Error: No stories fetched")
            sys.exit(1)
        
        logger.info("Fetched %d stories", len(stories))
        
        generator = ReportGenerator(openai_api_key, openai_base_url, openai_model)
        webhook = DiscordWebhook(discord_webhook_url)

        # Step 2: Per-article processing loop
        story_messages = []
        max_items = min(5, len(stories))
        for index, story in enumerate(stories[:max_items], start=1):
            logger.info("Generating summary for story %d: %s", index, story.get("title"))
            message = generator.generate_story_summary(story, index)
            if not message:
                logger.error("✗ Failed to generate summary for story %d; skipping this story", index)
                continue
            if len(message.strip()) < MIN_SUMMARY_LENGTH:
                logger.warning("Story %d summary too short; skipping from overall summary", index)
                continue
            story_messages.append(message)
            logger.info("Posting story %d message to Discord...", index)
            if not webhook.post_message(message):
                logger.error("✗ Failed to post story %d message to Discord", index)
                sys.exit(1)
        
        # Step 3: Overall summary
        if not story_messages:
            logger.error("Error: No successful story summaries generated; aborting overall summary generation")
            sys.exit(1)

        logger.info("Generating overall summary...")
        overall_summary = generator.generate_overall_summary(story_messages)

        # Validate overall summary before posting
        if overall_summary is None:
            logger.warning("Overall summary generation returned None. Using fallback message.")
            overall_summary = "⚠ 全体の要約を生成できませんでしたが、個別の記事サマリーは上記をご参照ください。"
        else:
            overall_summary_stripped = overall_summary.strip()
            if not overall_summary_stripped or len(overall_summary_stripped) < MIN_SUMMARY_LENGTH:
                logger.warning(
                    "Overall summary seems too short or empty (length=%d). Using fallback message.",
                    len(overall_summary_stripped),
                )
                overall_summary = (
                    "⚠ 全体の要約を十分に生成できませんでしたが、上記の各記事サマリーから本日の動向を確認してください。"
                )

        logger.info("Posting overall summary to Discord...")
        if not webhook.post_message(overall_summary):
            logger.error("✗ Failed to post overall summary to Discord")
            sys.exit(1)
        logger.info("✓ Report successfully posted to Discord!")
        logger.info("FINAL OVERALL SUMMARY:\n%s", overall_summary)
            
    except Exception as e:
        logger.exception("Error in main execution: %s", e)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
