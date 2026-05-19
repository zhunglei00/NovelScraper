"""
章节链接发现模块
从页面中提取同域名下的其他章节链接
"""

import re
import logging
from urllib.parse import urljoin, urlparse, parse_qs
from dataclasses import dataclass

from bs4 import BeautifulSoup

from scraper import fetch_page

logger = logging.getLogger(__name__)


@dataclass
class ChapterLink:
    """章节链接"""

    title: str  # 链接文本
    url: str  # 完整 URL
    tid: str = ""  # 帖子 ID（如果有）
    cid: str = ""  # 书库 ID（如果有）


def _normalize_url(href: str, base_url: str) -> str | None:
    """将相对 URL 转为完整 URL，过滤无效链接"""
    if (
        not href
        or href.startswith("javascript")
        or href.startswith("#")
        or href.startswith("mailto")
    ):
        return None
    full_url = urljoin(base_url, href)
    return full_url


def _is_same_domain(url1: str, url2: str) -> bool:
    """检查两个 URL 是否在同一域名下"""
    p1 = urlparse(url1)
    p2 = urlparse(url2)
    return p1.netloc == p2.netloc


def _is_novel_link(href: str) -> bool:
    """判断链接是否是小说内容链接（threadview 或 bookview）"""
    return (
        "threadview" in href
        or "bookview" in href
        or "act=bookview" in href
        or "act=threadview" in href
    )


def find_chapter_links(url: str) -> list[ChapterLink]:
    """从指定页面中发现同域名下的小说章节链接

    逻辑：
    1. 抓取页面
    2. 在页面内容区域（<pre> 或 content-section）内查找所有超链接
    3. 过滤：同域名 + 是小说内容链接
    4. 去重
    """
    html = fetch_page(url)
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    links: list[ChapterLink] = []
    seen_urls: set[str] = set()

    # 优先在内容区域查找链接
    search_areas = []

    # threadview: content-section
    content_section = soup.find("div", id="content-section")
    if content_section:
        search_areas.append(content_section)

    # bookview: show_content
    show_content = soup.find("td", class_="show_content")
    if show_content:
        search_areas.append(show_content)

    # 如果内容区域没找到，搜索整个页面
    if not search_areas:
        search_areas.append(soup)

    for area in search_areas:
        for a_tag in area.find_all("a"):
            href = a_tag.get("href", "")
            text = a_tag.get_text(strip=True)

            if not text:
                continue

            full_url = _normalize_url(href, url)
            if not full_url:
                continue

            # 检查同域名
            if not _is_same_domain(full_url, url):
                continue

            # 检查是否是小说内容链接
            if not _is_novel_link(full_url):
                continue

            # 去重
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            # 提取 ID
            parsed = urlparse(full_url)
            params = parse_qs(parsed.query)
            tid = params.get("tid", [""])[0]
            cid = params.get("cid", [""])[0]

            links.append(
                ChapterLink(
                    title=text,
                    url=full_url,
                    tid=tid,
                    cid=cid,
                )
            )

    return links


def find_chapter_links_recursive(
    url: str,
    max_depth: int = 2,
    delay: float = 1.0,
) -> list[ChapterLink]:
    """递归发现章节链接

    对于目录页，其中可能包含指向其他目录页的链接，
    需要递归深入发现所有章节链接。

    Args:
        url: 起始 URL
        max_depth: 最大递归深度（默认 2，避免过深）
        delay: 请求间隔（秒）

    Returns:
        去重后的章节链接列表
    """
    import time

    all_links: list[ChapterLink] = []
    seen_urls: set[str] = {url}
    visited_urls: set[str] = set()

    # BFS
    queue: list[tuple[str, int]] = [(url, 0)]

    while queue:
        current_url, depth = queue.pop(0)

        if current_url in visited_urls:
            continue
        visited_urls.add(current_url)

        if depth > max_depth:
            continue

        links = find_chapter_links(current_url)

        for link in links:
            if link.url not in seen_urls:
                seen_urls.add(link.url)
                all_links.append(link)
                # 如果该链接页面也可能包含更多章节链接，加入队列
                queue.append((link.url, depth + 1))

        if delay > 0:
            time.sleep(delay)

    return all_links


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # 测试：从目录页发现章节链接
    url = "https://www.cool18.com/bbs4/index.php?app=forum&act=threadview&tid=14131297"
    links = find_chapter_links(url)
    for link in links[:20]:
        print(f"  {link.title[:50]:50s} -> {link.url}")
