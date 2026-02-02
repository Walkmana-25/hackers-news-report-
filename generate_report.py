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
import trafilatura
from readability import Document
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

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


class WebContentFetcher:
    """Fetches and extracts article content from URLs"""

    def __init__(self, timeout: int = 10, max_content_chars: int = 3000):
        """Initialize fetcher with timeout configuration"""
        self.timeout = timeout
        self.max_content_chars = max_content_chars
        self.user_agent = "Mozilla/5.0 (compatible; HN-Report-Generator/1.0)"

    def fetch_article_content(self, url: str) -> Dict[str, Optional[str]]:
        """
        Fetch and extract article content from URL

        Args:
            url: The article URL to fetch

        Returns:
            Dictionary with:
                - 'content': Extracted article text (or None if failed)
                - 'title': Article title from page (or None)
                - 'error': Error message if failed (or None)
                - 'method': Which extraction method succeeded
        """
        # Check if URL should be skipped
        if self._should_skip_url(url):
            return {
                'content': None,
                'title': None,
                'error': 'URL skipped (internal or unsupported type)',
                'method': None
            }

        try:
            # Fetch the page
            headers = {'User-Agent': self.user_agent}
            response = requests.get(url, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            html_content = response.text

            # Try extraction methods in order
            content = None
            method = None

            # Method 1: Trafilatura (primary)
            content = self._extract_with_trafilatura(html_content)
            if content:
                method = 'trafilatura'

            # Method 2: Readability (fallback)
            if not content:
                content = self._extract_with_readability(html_content)
                if content:
                    method = 'readability'

            # Method 3: Basic text extraction (last resort)
            if not content:
                content = self._extract_basic_text(html_content)
                if content:
                    method = 'basic'

            if content:
                # Truncate if necessary
                content = self._truncate_content(content)
                logger.info("Successfully fetched article content using %s: %d chars", method, len(content))
                return {
                    'content': content,
                    'title': None,  # Could extract title if needed
                    'error': None,
                    'method': method
                }
            else:
                return {
                    'content': None,
                    'title': None,
                    'error': 'No content could be extracted',
                    'method': None
                }

        except requests.exceptions.Timeout:
            logger.warning("Timeout fetching article from %s", url)
            return {
                'content': None,
                'title': None,
                'error': 'Request timeout',
                'method': None
            }
        except requests.exceptions.HTTPError as e:
            logger.warning("HTTP error fetching article from %s: %s", url, e)
            return {
                'content': None,
                'title': None,
                'error': f'HTTP error: {e}',
                'method': None
            }
        except Exception as e:
            logger.warning("Error fetching article from %s: %s", url, e)
            return {
                'content': None,
                'title': None,
                'error': str(e),
                'method': None
            }

    def _should_skip_url(self, url: str) -> bool:
        """Check if URL should be skipped (HN internal, etc.)"""
        if not url:
            return True
        # Skip Hacker News internal URLs
        if 'news.ycombinator.com' in url:
            return True
        # Skip PDF and other non-HTML files
        skip_extensions = ('.pdf', '.zip', '.exe', '.dmg', '.iso')
        if url.lower().endswith(skip_extensions):
            return True
        return False

    def _extract_with_trafilatura(self, html: str) -> Optional[str]:
        """Extract article content using Trafilatura"""
        try:
            content = trafilatura.extract(
                html,
                include_comments=False,
                include_tables=False,
                no_fallback=False
            )
            if content and len(content.strip()) > 50:
                return content.strip()
        except Exception as e:
            logger.debug("Trafilatura extraction failed: %s", e)
        return None

    def _extract_with_readability(self, html: str) -> Optional[str]:
        """Extract article content using readability-lxml"""
        try:
            doc = Document(html)
            content = doc.summary()
            # Extract text from the HTML summary
            soup = BeautifulSoup(content, 'lxml')
            # Get all paragraph text
            paragraphs = soup.find_all('p')
            text = ' '.join(p.get_text() for p in paragraphs if p.get_text())
            if text and len(text.strip()) > 50:
                return text.strip()
        except Exception as e:
            logger.debug("Readability extraction failed: %s", e)
        return None

    def _extract_basic_text(self, html: str) -> Optional[str]:
        """Basic text extraction as last resort"""
        try:
            soup = BeautifulSoup(html, 'lxml')
            # Remove script, style, nav, footer elements
            for element in soup(['script', 'style', 'nav', 'footer', 'header', 'aside']):
                element.decompose()
            # Get all paragraph text
            paragraphs = soup.find_all('p')
            text = ' '.join(p.get_text() for p in paragraphs if p.get_text())
            if text and len(text.strip()) > 50:
                return text.strip()
        except Exception as e:
            logger.debug("Basic text extraction failed: %s", e)
        return None

    def _truncate_content(self, content: str) -> str:
        """
        Intelligently truncate content to fit within token limits

        Strategy: Keep first part (intro) and last part (conclusion),
        truncate middle if needed.
        """
        if len(content) <= self.max_content_chars:
            return content

        # Keep first 2/3 and last 1/3 within limit
        first_part_size = int(self.max_content_chars * 0.6)
        last_part_size = self.max_content_chars - first_part_size - 20  # 20 chars for ellipsis

        first_part = content[:first_part_size]
        last_part = content[-last_part_size:]

        return f"{first_part}\n\n...（中略）...\n\n{last_part}"


class ReportGenerator:
    """Generates report using OpenAI-compatible API"""

    # Check if article fetching is enabled
    ENABLE_ARTICLE_FETCH = os.getenv("ENABLE_ARTICLE_FETCH", "true").lower() == "true"

    def __init__(self, api_key: str, base_url: Optional[str] = None, model: Optional[str] = None):
        """Initialize OpenAI client with custom base URL if provided"""
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url

        self.client = OpenAI(**client_kwargs)
        # Use provided model, or get from env, or use default
        self.model = model or os.getenv("OPENAI_MODEL") or "gpt-3.5-turbo"

        # Initialize content fetcher if enabled
        if self.ENABLE_ARTICLE_FETCH:
            self.content_fetcher = WebContentFetcher(
                timeout=int(os.getenv("ARTICLE_FETCH_TIMEOUT", "10")),
                max_content_chars=int(os.getenv("MAX_ARTICLE_CONTENT_CHARS", "1500"))
            )
        else:
            self.content_fetcher = None
    
    def generate_story_summary(self, story: Dict, index: int) -> str:
        """Generate summary for a single story"""
        title = story.get("title", "No title")
        url = story.get("url")
        hn_url = f"https://news.ycombinator.com/item?id={story.get('id', '')}"
        # Use original URL if available, otherwise use HN discussion URL
        display_url = url or hn_url
        score = story.get("score", 0)
        comments = story.get("top_comments", [])

        # Fetch article content if available and enabled
        article_content = None
        fetch_error = None
        if url and self.content_fetcher:
            fetch_result = self.content_fetcher.fetch_article_content(url)
            if fetch_result['content']:
                article_content = fetch_result['content']
                logger.info("Successfully fetched article content for story %d: %d chars using %s",
                           index, len(article_content), fetch_result['method'])
            else:
                fetch_error = fetch_result.get('error')
                logger.warning("Could not fetch article content for story %d: %s", index, fetch_error)

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

        # Build prompt with actual article content
        if article_content:
            content_section = f"""
【記事本文】
{article_content}
"""
        elif url and fetch_error:
            content_section = f"""
【記事本文】
※記事の本文を取得できませんでした（{fetch_error}）。
タイトルとURL情報から記事の概要を推測してください。
"""
        else:
            content_section = """
【記事本文】
※Ask HN / Show HN のため外部記事がありません。
Hacker News上の情報から内容を推測してください。
"""

        prompt = f"""Hacker Newsのトップ記事 {index} を要約してください。
タイトル: {title}
URL: {display_url}
スコア: {score}
{content_section}
【Hacker News上の主なコメント】
{comments_joined}

以下の形式で短い日本語メッセージを作成してください:
- タイトルとURL
- 記事内容の要約（実際の記事内容に基づいて簡潔に）
- コメントから読み取れるポイントの要約
- なぜ重要か/興味深いかを一文
"""
        # Log prompt length for debugging
        logger.info("Generating summary for story %d with prompt length: %d chars", index, len(prompt))

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "あなたはテクノロジーニュースのライターです。簡潔にまとめてください。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.6,
                max_tokens=800
            )
            content = response.choices[0].message.content
            logger.info("AI response length for story %d: %d chars", index, len(content or ""))
            if isinstance(content, list):
                # Some providers return list of content blocks
                content = "".join(
                    block.get("text", "") if isinstance(block, dict) else str(block)
                    for block in content
                )

            if not content or not content.strip():
                logger.warning("Empty summary returned for story %d; using fallback text.", index)
                content = (
                    f"{title} ({display_url}) の要約を生成できませんでした。"
                    f" スコア: {score}。主要コメント: {comments_joined}"
                )
            return content
        except Exception as e:
            logger.exception("Error generating story summary: %s", e)
            return f"{title} ({display_url}) の要約生成に失敗しました。"

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
        logger.info("Generating overall summary with prompt length: %d chars", len(prompt))

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "あなたはテクノロジーニュース編集者です。全体のまとめを作成してください。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5,
                max_tokens=600
            )
            content = response.choices[0].message.content
            logger.info("Overall summary AI response length: %d chars", len(content or ""))
            return content
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
