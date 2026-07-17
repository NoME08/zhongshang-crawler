"""主程序入口"""

import json
import os
import time
import random
import logging
from datetime import datetime

import config
from crawler import (
    fetch_page, parse_list_page, parse_detail_page,
    load_processed_urls, save_processed_url,
)
from downloader import download_image
from reformat_docx import generate_formatted_docx, export_pdfs

# --- 日志配置 ---
os.makedirs(config.LOGS_DIR, exist_ok=True)
os.makedirs(config.OUTPUT_DIR, exist_ok=True)
os.makedirs(config.IMAGES_DIR, exist_ok=True)

logger = logging.getLogger("spider")
logger.setLevel(logging.DEBUG)

console = logging.StreamHandler()
console.setLevel(logging.INFO)
console.setFormatter(logging.Formatter("%(asctime)s | %(message)s", datefmt="%H:%M:%S"))
logger.addHandler(console)

file_handler = logging.FileHandler(
    os.path.join(config.LOGS_DIR, "spider.log"), encoding="utf-8"
)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(
    logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s")
)
logger.addHandler(file_handler)


def _save_json(data, filepath):
    """保存 JSON 文件"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _collect_latest(all_links, processed_urls):
    """latest 模式：从总列表按时间倒序，抓取最新 N 篇"""
    import math
    pages = math.ceil(config.LATEST_COUNT / config.ARTICLES_PER_PAGE)
    list_url_base = f"{config.BASE_URL}/news/viewindustry/"
    logger.info(f"  模式: 按时间倒序, {config.LATEST_COUNT} 篇 ({pages} 页)")

    for page_num in range(1, pages + 1):
        list_url = f"{list_url_base}?pageNum={page_num}"
        html = fetch_page(list_url)
        if not html:
            break
        articles = parse_list_page(html)
        if not articles:
            break
        _add_articles(all_links, articles, processed_urls,
                      f"  第 {page_num} 页")
        time.sleep(random.uniform(config.LIST_DELAY_MIN, config.LIST_DELAY_MAX))


def _collect_by_category(all_links, processed_urls):
    """by_category 模式：8 个板块各抓取最新 N 篇"""
    import math
    pages = math.ceil(config.PER_CATEGORY_COUNT / config.ARTICLES_PER_PAGE)
    logger.info(f"  模式: 按板块, 每板块 {config.PER_CATEGORY_COUNT} 篇 ({pages} 页)")

    for cat_name, cat_path in config.SUBCATEGORIES:
        logger.info(f"  板块: {cat_name}")
        for page_num in range(1, pages + 1):
            list_url = f"{config.BASE_URL}{cat_path}?pageNum={page_num}"
            html = fetch_page(list_url)
            if not html:
                break
            articles = parse_list_page(html)
            if not articles:
                break
            _add_articles(all_links, articles, processed_urls,
                          f"    第 {page_num} 页")
            time.sleep(random.uniform(config.LIST_DELAY_MIN, config.LIST_DELAY_MAX))


def _add_articles(all_links, articles, processed_urls, label):
    """去重并添加到待抓取列表"""
    new_count = 0
    for art in articles:
        url = art["url"]
        if url not in processed_urls and url not in all_links:
            all_links[url] = art
            new_count += 1
    logger.info(f"{label}: {len(articles)} 篇, 新增 {new_count} 篇")


def main():
    logger.info("=" * 50)
    logger.info("中商情报网爬虫启动")
    logger.info("=" * 50)

    processed_urls = load_processed_urls(config.PROCESSED_URLS_FILE)
    logger.info(f"已处理文章数: {len(processed_urls)}")

    # ---- 阶段 1：收集文章链接 ----
    logger.info("阶段 1/3: 收集文章列表...")
    all_links: dict[str, dict] = {}

    if config.CRAWL_MODE == "latest":
        _collect_latest(all_links, processed_urls)
    elif config.CRAWL_MODE == "by_category":
        _collect_by_category(all_links, processed_urls)
    else:
        logger.error(f"未知抓取模式: {config.CRAWL_MODE}")
        return

    logger.info(f"共收集 {len(all_links)} 篇待抓取文章")
    if not all_links:
        logger.info("无新文章，退出")
        return

    # ---- 阶段 2：抓取详情页 + 下载图片 ----
    logger.info("阶段 2/3: 抓取详情页...")
    results = []
    total = len(all_links)

    for i, (url, basic_info) in enumerate(all_links.items(), 1):
        logger.info(f"  [{i}/{total}] {basic_info['title'][:50]}...")

        html = fetch_page(url)
        if not html:
            save_processed_url(config.PROCESSED_URLS_FILE, url)
            continue

        try:
            article = parse_detail_page(html, url)
        except Exception as e:
            logger.error(f"  解析失败: {url} - {e}")
            save_processed_url(config.PROCESSED_URLS_FILE, url)
            continue

        if not article:
            save_processed_url(config.PROCESSED_URLS_FILE, url)
            continue

        article["tag"] = basic_info.get("tag", "")

        for item in article.get("content", []):
            if item["type"] == "image":
                local_path = download_image(
                    item["url"],
                    article.get("publish_time", ""),
                    article.get("id", ""),
                )
                if local_path:
                    item["local_path"] = local_path

        results.append(article)
        save_processed_url(config.PROCESSED_URLS_FILE, url)
        time.sleep(random.uniform(config.DETAIL_DELAY_MIN, config.DETAIL_DELAY_MAX))

    logger.info(f"成功抓取 {len(results)} 篇文章")

    # ---- 阶段 3：导出 ----
    logger.info("阶段 3/3: 导出数据...")

    today = datetime.now().strftime("%Y-%m-%d")
    output_docx = os.path.join(config.OUTPUT_DIR, f"output_{today}.docx")

    output_data = {
        "crawl_time": datetime.now().isoformat(),
        "total_articles": len(results),
        "articles": results,
    }
    _save_json(output_data, config.DATA_JSON_FILE)

    logger.info("生成格式化 Word 文档...")
    # 导出 PDF + 打包 zip
    pdf_dir = os.path.join(config.OUTPUT_DIR, f"pdf_{today}")
    zip_path = os.path.join(config.OUTPUT_DIR, f"中商情报_{today}.zip")
    logger.info("导出 PDF...")
    try:
        export_pdfs(config.DATA_JSON_FILE, config.IMAGES_DIR, pdf_dir)
    except RuntimeError as e:
        logger.error(f"PDF 转换失败: {e}")
        logger.info("提示：请安装 LibreOffice 后重试")
        logger.info(f"Word 文档已生成: {output_docx}")
        return

    logger.info("打包 zip...")
    import shutil
    shutil.make_archive(zip_path.replace(".zip", ""), "zip", pdf_dir)
    shutil.rmtree(pdf_dir)

    logger.info("=" * 50)
    logger.info(f"完成！共抓取 {len(results)} 篇文章")
    logger.info(f"下载: {zip_path}")
    logger.info(f"JSON: {config.DATA_JSON_FILE}")
    logger.info(f"Word: {output_docx}")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
