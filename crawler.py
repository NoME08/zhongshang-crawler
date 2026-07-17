"""核心爬虫模块"""

import re
import time
import random
import logging
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

import config

logger = logging.getLogger("spider")


def fetch_page(url):
    """请求页面，带重试和指数退避"""
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            resp = requests.get(
                url,
                headers=config.HEADERS,
                timeout=config.REQUEST_TIMEOUT,
            )
            resp.encoding = "utf-8"
            if resp.status_code == 200:
                return resp.text
            elif resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 60))
                logger.warning(f"429 限流: {url}, 等待 {wait}s")
                time.sleep(wait)
            elif resp.status_code in (502, 503):
                logger.warning(f"HTTP {resp.status_code}: {url}, attempt {attempt}")
            else:
                logger.warning(f"HTTP {resp.status_code}: {url}")
                return None
        except requests.RequestException as e:
            logger.warning(f"请求异常: {url} - {e}, attempt {attempt}")

        if attempt < config.MAX_RETRIES:
            sleep_time = config.RETRY_BACKOFF ** attempt
            time.sleep(sleep_time)

    logger.error(f"请求失败（已达最大重试次数）: {url}")
    return None


def parse_list_page(html):
    """解析列表页，返回文章基本信息列表"""
    soup = BeautifulSoup(html, "lxml")
    articles = []

    for li in soup.select("div.content_list_23 ul li"):
        # 标题 + 详情页 URL（兼容 _231 和 _23 两种类名）
        title_link = (
            li.select_one("div.content_list_title_231 a")
            or li.select_one("div.content_list_title_23 a")
        )
        if not title_link:
            continue
        title = title_link.get("title", "").strip() or title_link.get_text(strip=True)
        detail_url = title_link.get("href", "")
        if detail_url and not detail_url.startswith("http"):
            detail_url = urljoin(config.BASE_URL, detail_url)

        # 发布日期（兼容 _232 和 _23 两种类名；子分类页日期在 div 文本内）
        font_div = (
            li.select_one("div.content_list_font_232")
            or li.select_one("div.content_list_font_23")
        )
        pub_date = ""
        tag = ""
        if font_div:
            date_b = font_div.select_one("b")
            if date_b:
                pub_date = date_b.get_text(strip=True)
            else:
                # 子分类页：日期是文本末尾的 YYYY-MM-DD
                full_text = font_div.get_text(strip=True)
                date_match = re.search(r"(\d{4}-\d{2}-\d{2})", full_text)
                if date_match:
                    pub_date = date_match.group(1)
            tag_elem = font_div.select_one("a")
            tag = tag_elem.get_text(strip=True) if tag_elem else ""

        # 缩略图（仅记录，不下载）
        thumb_elem = li.select_one("div.content_list_img_23 img")
        thumbnail = thumb_elem.get("src", "") if thumb_elem else ""

        # 从 URL 提取文章 ID 和日期
        article_id = ""
        match = re.search(r"/news/chanye/(\d{8})/(\w+)\.shtml", detail_url)
        if match:
            article_id = match.group(2)
            if not pub_date:
                pub_date = f"{match.group(1)[:4]}-{match.group(1)[4:6]}-{match.group(1)[6:8]}"

        articles.append({
            "title": title,
            "url": detail_url,
            "publish_date": pub_date,
            "tag": tag,
            "thumbnail": thumbnail,
            "article_id": article_id,
        })

    return articles


def parse_detail_page(html: str, url):
    """解析文章详情页，提取完整内容"""
    soup = BeautifulSoup(html, "lxml")

    # --- 标题 ---
    title = ""
    h1 = soup.select_one("h1")
    if h1:
        title = h1.get_text(strip=True)
    if not title:
        title_tag = soup.select_one("title")
        if title_tag:
            title = title_tag.get_text(strip=True)
            # 去掉后缀 " - 中商情报网"
            title = re.sub(r"\s*[-_|]\s*中商情报网.*$", "", title)

    # --- 发布时间 ---
    publish_time = ""
    time_match = re.search(
        r"发布日期[：:]\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})", html
    )
    if time_match:
        publish_time = time_match.group(1)

    # --- 来源 ---
    source = "中商产业研究院"  # 默认值
    source_match = re.search(r"来源[：:]\s*(.+?)(?:<|[\n\r])", html)
    if source_match:
        source = source_match.group(1).strip()

    # --- 正文内容 ---
    content = []

    # 尝试定位正文容器
    article_body = (
        soup.select_one("div.detail_content_text")
        or soup.select_one("div.article-content")
        or soup.select_one("div.detail-content")
        or soup.select_one("article")
    )

    if article_body:
        # --- 从 DOM 中删除「相关文章/广告/报告推荐」容器 ---
        for suspect in article_body.select(
            '[class*="related"], [class*="relevant"], [class*="recommend"],'
            '[class*="about-news"], [class*="xgyd"], [class*="hot_news"],'
            '[class*="project_right"], [class*="ad_box"], [class*="news_about"],'
            '[class*="hot_list"], [class*="theme_box"], [class*="content_box6"]'
        ):
            suspect.decompose()
        for container in article_body.find_all(
            ['div', 'ul', 'section'], recursive=False
        ):
            news_links = container.select('a[href*="/news/chanye/"]')
            if len(news_links) >= 3:
                container.decompose()

        # --- 按子元素顺序遍历，保持图文交错不丢序 ---
        body_stop_ref = [False]  # 用 list 实现引用传递
        for child in article_body.children:
            if body_stop_ref[0]:
                break
            if not hasattr(child, 'name'):
                continue  # 跳过空白文本节点

            if child.name in ("p", "span"):
                _process_block_element(child, content, body_stop_ref)
            elif child.name == "img":
                src = _normalize_img_src(child.get("src", ""))
                if src and _is_content_image(src):
                    content.append({
                        "type": "image", "url": src, "local_path": "",
                    })
            elif child.name in ("div", "section", "figure", "li"):
                # 嵌套容器：递归处理
                for sub in child.children:
                    if not hasattr(sub, 'name'):
                        continue
                    if sub.name in ("p", "span"):
                        _process_block_element(sub, content, body_stop_ref)
                    elif sub.name == "img":
                        src = _normalize_img_src(sub.get("src", ""))
                        if src and _is_content_image(src):
                            content.append({
                                "type": "image", "url": src, "local_path": "",
                            })
            if body_stop_ref[0]:
                break

    # --- 提取英文数据来源（"数据来源：xxx整理"） ---
    data_source = ""
    for item in content:
        if item["type"] == "data_source":
            data_source = item["value"]
            break

    # 移除 content 中的 data_source 条目，统一用顶层字段
    content = [c for c in content if c["type"] != "data_source"]

    # --- 后向清理垃圾尾部（页脚 + 相关文章推荐区） ---
    content = _trim_garbage_tail(content)

    # --- article_id ---
    article_id = ""
    match = re.search(r"/news/chanye/\d{8}/(\w+)\.shtml", url)
    if match:
        article_id = match.group(1)

    # --- 标签 ---
    tags = []
    tag_links = soup.select("div.content_list_font_232 a")
    for t in tag_links:
        tag_text = t.get_text(strip=True)
        if tag_text:
            tags.append(tag_text)

    return {
        "id": article_id,
        "title": title,
        "url": url,
        "publish_time": publish_time,
        "source": source,
        "tags": tags,
        "content": content,
        "data_source": data_source,
    }


def _normalize_img_src(src):
    """补全图片 URL"""
    if not src:
        return ""
    if src.startswith("//"):
        return "https:" + src
    if src.startswith("/"):
        return urljoin(config.BASE_URL, src)
    return src


def _process_block_element(elem, content, stop_ref):
    """从 <p>/<span> 中提取文本或图片，保持图文交错顺序"""
    imgs = elem.find_all('img', recursive=False)
    if imgs:
        # 包含图片的段落：按子元素顺序提取
        for sub in elem.children:
            if stop_ref[0]:
                return
            if isinstance(sub, str):
                text = sub.strip()
                if text:
                    if _is_garbage_boundary(text):
                        stop_ref[0] = True
                        return
                    if "数据来源" in text or "资料来源" in text:
                        content.append({"type": "data_source", "value": text})
                    else:
                        content.append({"type": "text", "value": text})
            elif hasattr(sub, 'name') and sub.name == 'img':
                src = _normalize_img_src(sub.get("src", ""))
                if src and _is_content_image(src):
                    content.append({"type": "image", "url": src, "local_path": ""})
    else:
        # 纯文本段落
        text = elem.get_text(strip=True)
        if not text:
            return
        if _is_garbage_boundary(text):
            stop_ref[0] = True
            return
        if "数据来源" in text or "资料来源" in text:
            content.append({"type": "data_source", "value": text})
        else:
            content.append({"type": "text", "value": text})


def _is_content_image(src):
    """判断是否为正文图片（排除缩略图、装饰图）"""
    # 缩略图
    if "-248x137" in src:
        return False
    # 装饰图标
    skip_patterns = ["report_icon", "zt_", "arrow_right", "project_right",
                     "hot_icon", "share_icon", "tips_icon", "page_home_icon",
                     "logogai", "weibo", "weix", "2code", "askci-header",
                     "askci1807"]
    for pat in skip_patterns:
        if pat in src.lower():
            return False
    # 必须是 image1.askci.com 或相对路径
    if "image1.askci.com" in src or "/images/" in src:
        return True
    return False


def _is_garbage_boundary(text):
    """检测是否为垃圾段落边界（相关报告推荐 / 页脚信息）"""
    if not text:
        return False
    # 推销段落（"更多资料请参考中商产业研究院发布的..."）
    if text.startswith("更多资料请参考"):
        return True
    # 原始 HTML 残留
    if _has_html_leak(text):
        return True

    if len(text) < 150:
        # --- 明确页脚特征（最可靠的垃圾信号）---
        for pat in [r'粤ICP备', r'增值电信', r'Copyright',
                     r'关于我们\\|服务领域', r'关于我们[｜|]服务领域']:
            if re.search(pat, text):
                return True

        # --- 短文本（<60字）的排行榜/推荐标题 ---
        if len(text) < 60:
            # "2026年1月中国汽车销量前十企业（集团）排行榜（附榜单）"
            if re.search(r'排行榜', text):
                return True
            # "2026年1-5月全国固定资产投资同比下降4.1%（图）"
            if re.search(r'^\d{4}年\d{1,2}[月-].*（图）$', text):
                return True
            # "2024年上半年兰州市上市公司营业收入排行榜（附榜单）"
            if re.search(r'^\d{4}年.*排行榜', text):
                return True

        # --- 相关报告标题特征（中短文本） ---
        if len(text) < 120:
            # "2026-2031全球与中国XXX市场现状及未来发展趋势"
            if re.search(r'^\d{4}-\d{4}全球与中国.*市场现状及未来发展趋势', text):
                return True
            # "2026-2031中国XXX市场现状研究分析与发展前景预测报告"
            if re.search(r'^\d{4}-\d{4}中国.*市场现状研究', text):
                return True
            # "2023-2028年中国XXX行业市场前景预测与发展趋势研究报告"
            if re.search(r'前景预测与发展趋势研究', text):
                return True

        # --- 招股书/报告推广标题（中长文本）---
        for pat in [r'招股说明书', r'调研专题报告', r'可行性调研',
                     r'投资可行性', r'十四五规划']:
            if re.search(pat, text) and len(text) < 100:
                return True

    return False


def _has_html_leak(text):
    """检测文本中是否包含泄漏的 HTML 标记（嵌套标签解析失败导致）"""
    import re as _re
    return bool(_re.search(r'<\s*(?:br\b|p\b|img\b|div\b|span\b)', text))


def _trim_garbage_tail(content):
    """后向扫描：从 content 尾部删除垃圾段（页脚 + 相关文章推荐区）。

    策略：
    1. 从尾部找到明确的页脚标记（关于我们/Copyright/增值电信）
    2. 反向扫描，用 _is_garbage_boundary 判断每条文本是否为垃圾
    3. 遇到非垃圾文本立即停止，避免误删正文短条目（如政策列表）
    """
    if not content:
        return content

    _FOOTER_KW = ['Copyright', '粤ICP备', '增值电信', '关于我们|', '关于我们｜']

    # 1. 找页脚起始位置
    footer_idx = None
    for i in range(len(content) - 1, -1, -1):
        item = content[i]
        if item["type"] == "text" and any(kw in item["value"] for kw in _FOOTER_KW):
            footer_idx = i
            break

    if footer_idx is None:
        return content

    # 2. 反向扫描：只删除明确匹配垃圾模式的文本
    #    图片不参与 cut_idx 判定，靠文本边界自然截断
    cut_idx = footer_idx
    for i in range(footer_idx - 1, -1, -1):
        item = content[i]
        if item["type"] == "text":
            t = item["value"]
            if _has_html_leak(t) or any(kw in t for kw in _FOOTER_KW):
                cut_idx = i
                continue
            if _is_garbage_boundary(t):
                cut_idx = i
                continue
            # 不匹配任何垃圾特征 → 正文，停止扫描
            break
        elif item["type"] == "image":
            continue
        else:
            break

    return content[:cut_idx]


def load_processed_urls(filepath):
    """加载已处理的 URL 列表"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f if line.strip())
    except FileNotFoundError:
        return set()


def save_processed_url(filepath: str, url):
    """追加写入已处理 URL"""
    with open(filepath, "a", encoding="utf-8") as f:
        f.write(url + "\n")
        f.flush()
