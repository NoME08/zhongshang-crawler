"""图片下载模块"""

import os
import hashlib
from typing import Optional
import logging
import requests

import config

logger = logging.getLogger("spider")

# 全局图片去重：已下载的图片 URL
_downloaded_urls = {}  # url -> local_path


def _is_blacklisted(filepath):
    """检查图片是否在广告黑名单中（按 MD5 匹配）"""
    if not config.AD_IMAGE_HASHES:
        return False
    try:
        with open(filepath, "rb") as f:
            h = hashlib.md5(f.read()).hexdigest()
        return h in config.AD_IMAGE_HASHES
    except Exception:
        return False


def download_image(img_url, article_date, article_id):
    """
    下载单张图片。
    返回本地路径，失败返回 None。
    自动去重：相同 URL 只下载一次。
    """
    # 去重检查
    if img_url in _downloaded_urls:
        return _downloaded_urls[img_url]

    # 提取文件扩展名
    ext = ".jpg"
    if ".png" in img_url.lower():
        ext = ".png"
    elif ".jpeg" in img_url.lower() or ".jpg" in img_url.lower():
        ext = ".jpg"
    elif ".gif" in img_url.lower():
        ext = ".gif"
    elif ".webp" in img_url.lower():
        ext = ".webp"

    # 构造本地路径
    date_str = article_date.replace("-", "")[:8] if article_date else "unknown"
    img_dir = os.path.join(config.IMAGES_DIR, date_str)
    os.makedirs(img_dir, exist_ok=True)

    # 用图片 URL 的 hash 作为文件名，避免过长
    filename = f"{article_id}_{hash(img_url) & 0x7FFFFFFF:08x}{ext}"
    local_path = os.path.join(img_dir, filename)

    # 如果文件已存在，跳过下载
    if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
        _downloaded_urls[img_url] = local_path
        return local_path

    # 下载
    try:
        resp = requests.get(img_url, headers=config.HEADERS, timeout=30)
        resp.raise_for_status()

        with open(local_path, "wb") as f:
            f.write(resp.content)

        file_size = os.path.getsize(local_path)
        if file_size == 0:
            os.remove(local_path)
            logger.warning(f"图片为空: {img_url}")
            return None

        # MD5 黑名单：已知广告图直接丢弃
        if _is_blacklisted(local_path):
            os.remove(local_path)
            logger.debug(f"跳过广告图(黑名单): {os.path.basename(local_path)}")
            _downloaded_urls[img_url] = None  # 标记已处理，不重复下载
            return None

        logger.debug(f"图片下载成功: {os.path.basename(local_path)} ({file_size} bytes)")
        _downloaded_urls[img_url] = local_path
        return local_path

    except Exception as e:
        logger.warning(f"图片下载失败: {img_url} - {e}")
        return None
