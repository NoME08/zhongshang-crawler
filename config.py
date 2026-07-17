"""配置文件"""

# --- 目标网站 ---
BASE_URL = "https://www.askci.com"

# 8 个子分类
SUBCATEGORIES = [
    ("产业链", "/news/viewindustry/ChanYeLian/"),
    ("市场规模", "/news/viewindustry/ShiChangGuiMo/"),
    ("竞争格局", "/news/viewindustry/JingZhengGeJu/"),
    ("投融资情况", "/news/viewindustry/TouRongZiQingKuang/"),
    ("政策法规", "/news/viewindustry/ZhengCeFaGui/"),
    ("产业研报", "/news/viewindustry/ChanYeYanBao/"),
    ("聚焦风口", "/news/viewindustry/JuJiaoFengKou/"),
    ("产业图谱", "/news/viewindustry/ChanYeTuPu/"),
]

# ============================================================
# 抓取模式（二选一，改这里）
#   "latest"       → 按时间倒序，抓取最新的 N 篇文章
#   "by_category"  → 按 8 个板块，每板块各抓取最新的 N 篇文章
# ============================================================
CRAWL_MODE = "latest"

# latest 模式：从总列表按时间倒序，抓取最新的 N 篇
LATEST_COUNT = 80         # 想抓多少填多少，自动算翻几页

# by_category 模式：8 个板块各抓取最新的 N 篇
PER_CATEGORY_COUNT = 30   # 每板块抓多少篇
# ============================================================

ARTICLES_PER_PAGE = 15

# --- 请求策略 ---
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}
REQUEST_TIMEOUT = 15

# 延时（秒）
LIST_DELAY_MIN = 1.0
LIST_DELAY_MAX = 3.0
DETAIL_DELAY_MIN = 2.0
DETAIL_DELAY_MAX = 5.0

# 重试
MAX_RETRIES = 3
RETRY_BACKOFF = 2  # 指数退避基数

# --- 输出路径 ---
OUTPUT_DIR = "output"
IMAGES_DIR = f"{OUTPUT_DIR}/images"
LOGS_DIR = "logs"
PROCESSED_URLS_FILE = f"{OUTPUT_DIR}/processed_urls.txt"
DATA_JSON_FILE = f"{OUTPUT_DIR}/data.json"

# 已知广告图 MD5 黑名单（永久过滤，不下载）
AD_IMAGE_HASHES = {
    "83a2daa21e160ebfb252678b486dc43e",  # 产业招商图谱+项目库 (原始 1568x426)
    "19408c0f195add29060e915ccce869e5",  # 产业招商图谱+项目库 (缩放 901x245)
    "de4a19389267480aac2a8c0031a17619",  # 产业招商图谱+项目库 (缩放 901x245)
}
