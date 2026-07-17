"""Flask Web 界面入口"""
import json
import os
import sys
import time
import random
import logging
import threading
from datetime import datetime

from flask import Flask, render_template, request, jsonify, Response, send_from_directory

import config
from crawler import (
    fetch_page, parse_list_page, parse_detail_page,
    load_processed_urls, save_processed_url,
)
from downloader import download_image
from reformat_docx import generate_formatted_docx, export_pdfs, generate_titles_docx

app = Flask(__name__)

# 进度状态（跨请求共享）
_progress = {"status": "idle", "current": 0, "total": 0, "msg": ""}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/crawl", methods=["POST"])
def api_crawl():
    """启动抓取任务（后台线程）"""
    global _progress
    if _progress["status"] == "running":
        return jsonify({"ok": False, "msg": "正在抓取中，请等待完成"})

    data = request.get_json()
    mode = data.get("mode", "latest")
    count = int(data.get("count", 80))

    _progress = {
        "status": "running", "current": 0, "total": 0, "msg": "准备中...",
        "mode": mode, "count": count,
    }
    thread = threading.Thread(target=_do_crawl, args=(mode, count), daemon=True)
    thread.start()
    return jsonify({"ok": True})


@app.route("/api/progress")
def api_progress():
    """SSE 流式推送进度"""
    def stream():
        last = None
        while True:
            current = json.dumps(_progress, ensure_ascii=False)
            if current != last:
                yield f"data: {current}\n\n"
                last = current
            if _progress["status"] in ("done", "error"):
                break
            time.sleep(0.3)
    return Response(stream(), mimetype="text/event-stream")


def _do_crawl(mode, count):
    global _progress
    os.makedirs(config.LOGS_DIR, exist_ok=True)
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    os.makedirs(config.IMAGES_DIR, exist_ok=True)

    try:
        processed_urls = load_processed_urls(config.PROCESSED_URLS_FILE)
        all_links: dict[str, dict] = {}

        # 甜蜜进度提示库
        SWEET_MSGS = [
            "💭 在茫茫网页里找到对你有用的那篇...",
            "☕ 喝杯咖啡等我，马上就好~",
            "🌸 每篇文章都在想你一次",
            "💕 这些数据很枯燥，但帮你抓数据不枯燥",
            "🎀 你的专属小助手正在努力工作",
            "✨ 再等一下下，好东西值得等",
            "🍰 抓完这篇，距离完成又近了一步",
            "🌙 今天的报告一定是最棒的",
            "💌 情报正在路上，先想想晚上吃什么",
            "🦋 能帮你做事真好",
            "🎵 文字在跳舞，图片在排队，马上就好",
        ]

        # 阶段 1
        _progress["msg"] = "✨ 正在为你收集情报..."
        import math
        if mode == "latest":
            pages = math.ceil(count / config.ARTICLES_PER_PAGE)
            list_url_base = f"{config.BASE_URL}/news/viewindustry/"
            for p in range(1, pages + 1):
                html = fetch_page(f"{list_url_base}?pageNum={p}")
                if not html: break
                arts = parse_list_page(html)
                if not arts: break
                for a in arts:
                    if a["url"] not in processed_urls and a["url"] not in all_links:
                        all_links[a["url"]] = a
                time.sleep(random.uniform(config.LIST_DELAY_MIN, config.LIST_DELAY_MAX))
        else:
            pages = math.ceil(count / config.ARTICLES_PER_PAGE)
            for _, cat_path in config.SUBCATEGORIES:
                for p in range(1, pages + 1):
                    html = fetch_page(f"{config.BASE_URL}{cat_path}?pageNum={p}")
                    if not html: break
                    arts = parse_list_page(html)
                    if not arts: break
                    for a in arts:
                        if a["url"] not in processed_urls and a["url"] not in all_links:
                            all_links[a["url"]] = a
                    time.sleep(random.uniform(config.LIST_DELAY_MIN, config.LIST_DELAY_MAX))

        # 阶段 2
        results = []
        items = list(all_links.items())
        _progress["total"] = len(items)
        _progress["current"] = 0

        for i, (url, basic_info) in enumerate(items, 1):
            _progress["current"] = i
            # 约 20% 的概率展示甜蜜提示
            if random.random() < 0.2:
                _progress["msg"] = random.choice(SWEET_MSGS)
            else:
                _progress["msg"] = basic_info["title"][:60]

            html = fetch_page(url)
            if not html:
                save_processed_url(config.PROCESSED_URLS_FILE, url)
                continue

            try:
                article = parse_detail_page(html, url)
            except Exception:
                save_processed_url(config.PROCESSED_URLS_FILE, url)
                continue

            if not article:
                save_processed_url(config.PROCESSED_URLS_FILE, url)
                continue

            article["tag"] = basic_info.get("tag", "")
            for item in article.get("content", []):
                if item["type"] == "image":
                    lp = download_image(item["url"], article.get("publish_time", ""), article.get("id", ""))
                    if lp:
                        item["local_path"] = lp

            results.append(article)
            save_processed_url(config.PROCESSED_URLS_FILE, url)
            time.sleep(random.uniform(config.DETAIL_DELAY_MIN, config.DETAIL_DELAY_MAX))

        # 阶段 3
        _progress["msg"] = "📝 正在为你排版..."
        today = datetime.now().strftime("%Y-%m-%d")
        output_docx = os.path.join(config.OUTPUT_DIR, f"output_{today}.docx")

        output_data = {
            "crawl_time": datetime.now().isoformat(),
            "total_articles": len(results),
            "articles": results,
        }
        with open(config.DATA_JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        # 生成整合版 docx
        _progress["msg"] = "📄 排版整合文档..."
        generate_formatted_docx(config.DATA_JSON_FILE, config.IMAGES_DIR, output_docx)

        # 生成标题 docx
        output_titles = os.path.join(config.OUTPUT_DIR, f"标题_{today}.docx")
        generate_titles_docx(config.DATA_JSON_FILE, output_titles)

        # 导出 PDF 并打包为 zip
        pdf_dir = os.path.join(config.OUTPUT_DIR, f"pdf_{today}")
        zip_path = os.path.join(config.OUTPUT_DIR, f"中商情报_{today}.zip")
        _progress["msg"] = "🎀 正在转 PDF，马上就好..."

        pdf_ok = True
        try:
            export_pdfs(config.DATA_JSON_FILE, config.IMAGES_DIR, pdf_dir)
        except RuntimeError as e:
            pdf_ok = False
            _progress["pdf_warning"] = str(e)

        if pdf_ok:
            _progress["msg"] = "🎁 打包礼物中..."
            import shutil
            shutil.make_archive(zip_path.replace(".zip", ""), "zip", pdf_dir)
            shutil.rmtree(pdf_dir)
            _progress["result_file"] = zip_path

        _progress["status"] = "done"
        _progress["sweet_msg"] = random.choice(SWEET_MSGS)
        msg = f"✨ 完成！{len(results)} 篇报告已备好～"
        if not pdf_ok:
            msg += "（PDF 暂不可用，可下载 Word 版）"
        _progress["msg"] = msg
        _progress["result_docx"] = output_docx
        _progress["result_titles"] = output_titles

    except Exception as e:
        _progress["status"] = "error"
        _progress["msg"] = str(e)


@app.route("/output/<path:filename>")
def download_file(filename):
    """提供输出文件下载"""
    return send_from_directory(config.OUTPUT_DIR, filename, as_attachment=True)


if __name__ == "__main__":
    print("淑琪同学专属 · 中商情报网爬虫")
    print("浏览器打开 http://localhost:1108")
    app.run(host="0.0.0.0", port=1108, debug=False)
