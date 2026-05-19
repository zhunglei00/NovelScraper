"""
网页抓取与正文提取模块
支持 cool18.com 的 threadview 和 bookview 两种页面格式
"""

import re
import time
import logging
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# 默认请求头
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# 需要过滤的水印文本
WATERMARK_PATTERN = re.compile(r"cool18\.com", re.IGNORECASE)
# 过滤 AI 检测相关文本
AI_DETECTION_PATTERN = re.compile(r"你认为此内容是否为AI生成.*", re.DOTALL)
# 过滤标签行前缀 (#系统 #NTL ...) —— 行首的连续 #标签
TAG_PREFIX_PATTERN = re.compile(r"^(\s*#[^\s]+\s*)+")
# 过滤 "标签：#xxx #yyy ..." 行尾标签列表
TAG_SUFFIX_PATTERN = re.compile(r"\s*标签[：:]\s*(#[^\s]+\s*)+\s*")


@dataclass
class ChapterContent:
    """单章内容"""

    title: str  # 章节标题
    content: str  # 正文内容
    url: str  # 来源 URL
    author: str = ""  # 作者


@dataclass
class NovelInfo:
    """小说信息"""

    title: str  # 小说名称
    chapters: list[ChapterContent]  # 章节列表
    url: str  # 入口 URL


def fetch_page(url: str, encoding: str = "utf-8", timeout: int = 30) -> str | None:
    """抓取网页内容"""
    try:
        resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
        resp.encoding = encoding
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as e:
        logger.error(f"抓取失败 {url}: {e}")
        return None


def _pre_to_text(pre_tag) -> str:
    """将 <pre> 标签内容转为保留换行的纯文本

    问题：cool18 的 <pre> 内嵌套了 <br> 和 <p> 作为换行标记，
    但 BeautifulSoup.get_text() 会直接丢弃这些标签，导致文字堆在一起。

    解决：在 get_text() 之前，将 <br>/<p> 替换为换行符占位，
    然后提取文本后再还原。
    """
    # 复制一份，避免修改原始 soup
    import copy

    pre_copy = copy.copy(pre_tag)

    # 将 <br> 替换为换行占位符
    for br in pre_copy.find_all("br"):
        br.replace_with("\n")

    # 将 <p> 替换为换行占位符（<p> 表示段落分隔，用两个换行）
    for p in pre_copy.find_all("p"):
        p.replace_with("\n" + p.get_text() + "\n")

    text = pre_copy.get_text()
    return text


def _clean_text(raw: str) -> str:
    """清理正文文本：去水印、去标签、规范化空白"""
    # 去除 cool18.com 水印（隐藏的 <font color=#E6E6DD>cool18.com</font>）
    text = WATERMARK_PATTERN.sub("", raw)
    # 去除行首标签（如 "#系统 #NTL #同人 ..."）
    text = TAG_PREFIX_PATTERN.sub("", text, count=1)
    # 去除 "标签：#xxx #yyy ..." 标签列表
    text = TAG_SUFFIX_PATTERN.sub("", text)
    # 将全角空格（\u3000）序列替换为单个换行（threadview 用全角空格分段）
    text = re.sub(r"\u3000{2,}", "\n", text)
    # 规范化连续空行为最多两个换行
    text = re.sub(r"\n{3,}", "\n\n", text)
    # 去除每行首尾空白
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)
    # 去除首尾空白
    text = text.strip()
    return text


def _extract_from_threadview(html: str, url: str) -> ChapterContent | None:
    """从 threadview 页面提取内容"""
    soup = BeautifulSoup(html, "lxml")

    # 提取标题
    title = ""
    if soup.title:
        title = soup.title.get_text(strip=True)
        # 去除 " - 禁忌书屋 cool18 酷18" 等后缀
        # 匹配 " - " 或 " – " 格式的分隔符（前后都有空格）
        title = re.split(r"\s+[-–—]\s+", title, maxsplit=1)[0].strip()

    # 正文在 <div id="content-section"> 内的 <pre> 标签中
    content_section = soup.find("div", id="content-section")
    if not content_section:
        logger.warning(f"未找到 content-section: {url}")
        return None

    pre = content_section.find("pre")
    if not pre:
        logger.warning(f"未找到 pre 标签: {url}")
        return None

    # 提取作者信息
    author = ""
    # 从标题中提取作者，格式如 "【武侠聊天群】（1-3）作者：牧天宇"
    author_match = re.search(r"作者[：:]\s*([^\s]+)", _pre_to_text(pre)[:200])
    if author_match:
        author = author_match.group(1).strip()

    raw_text = _pre_to_text(pre)
    clean = _clean_text(raw_text)

    return ChapterContent(title=title, content=clean, url=url, author=author)


def _extract_from_bookview(html: str, url: str) -> ChapterContent | None:
    """从 bookview 页面提取内容"""
    soup = BeautifulSoup(html, "lxml")

    # 提取标题
    title = ""
    title_tag = soup.find("font", size="6")
    if title_tag:
        title = title_tag.get_text(strip=True)
    elif soup.title:
        title = soup.title.get_text(strip=True)
        title = re.split(r"\s*[-–—]\s*", title)[0].strip()

    # 正文在 <td class="show_content"> 内的 <pre> 标签中
    td = soup.find("td", class_="show_content")
    if not td:
        logger.warning(f"未找到 show_content: {url}")
        return None

    pre = td.find("pre")
    if not pre:
        logger.warning(f"未找到 pre 标签: {url}")
        return None

    # 提取作者信息
    author = ""
    author_td = soup.find("td", height="23px")
    if author_td:
        author_text = author_td.get_text(strip=True)
        author_match = re.search(r"送交者:\s*(.+)", author_text)
        if author_match:
            author = author_match.group(1).strip()

    raw_text = _pre_to_text(pre)
    clean = _clean_text(raw_text)

    return ChapterContent(title=title, content=clean, url=url, author=author)


def extract_content(url: str, delay: float = 1.0) -> ChapterContent | None:
    """根据 URL 类型自动选择提取方法"""
    html = fetch_page(url)
    if not html:
        return None

    if delay > 0:
        time.sleep(delay)

    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    if "threadview" in url or "act=threadview" in url:
        return _extract_from_threadview(html, url)
    elif "bookview" in url or "act=bookview" in url:
        return _extract_from_bookview(html, url)
    else:
        # 尝试两种方式
        result = _extract_from_threadview(html, url)
        if result and len(result.content) > 100:
            return result
        result = _extract_from_bookview(html, url)
        if result and len(result.content) > 100:
            return result
        logger.warning(f"无法识别页面类型: {url}")
        return None


if __name__ == "__main__":
    # 测试
    logging.basicConfig(level=logging.INFO)
    # threadview 测试
    url1 = "https://www.cool18.com/bbs4/index.php?app=forum&act=threadview&tid=14567282"
    result = extract_content(url1)
    if result:
        print(f"标题: {result.title}")
        print(f"作者: {result.author}")
        print(f"内容长度: {len(result.content)}")
        print(f"内容预览: {result.content[:200]}")
