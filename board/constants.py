"""募集タイプ、時間帯、関東のエリア定義。"""

WEEKDAYS = "月火水木金土日"

POST_TYPES = [
    {
        "code": "with_ground",
        "label": "練習試合相手募集（グラウンドあり）",
        "short": "グラウンドあり",
        "description": "自分たちのグラウンドで相手を探す",
    },
    {
        "code": "without_ground",
        "label": "練習試合相手募集（グラウンドなし）",
        "short": "グラウンドなし",
        "description": "相手のグラウンドで試合したい",
    },
    {
        "code": "helper",
        "label": "助っ人募集",
        "short": "助っ人",
        "description": "足りない人数・ポジションを募る",
    },
]

TIME_SLOTS = [
    ("morning", "午前"),
    ("afternoon", "午後"),
    ("night", "ナイター"),
    ("allday", "終日"),
    ("custom", "時間を指定"),
]

PREFECTURES = [
    ("tokyo", "東京"),
    ("kanagawa", "神奈川"),
    ("saitama", "埼玉"),
    ("chiba", "千葉"),
    ("ibaraki", "茨城"),
    ("tochigi", "栃木"),
    ("gunma", "群馬"),
]

# code, ドロップダウン表示, 一覧・詳細の表示, 都道府県コード
AREAS = [
    {"code": "tokyo-23", "option": "23区", "label": "東京23区", "pref": "tokyo"},
    {"code": "tokyo-tama", "option": "多摩", "label": "東京・多摩", "pref": "tokyo"},
    {"code": "kanagawa-yokohama", "option": "横浜", "label": "神奈川・横浜", "pref": "kanagawa"},
    {"code": "kanagawa-kawasaki", "option": "川崎", "label": "神奈川・川崎", "pref": "kanagawa"},
    {"code": "kanagawa-miura", "option": "横須賀・三浦", "label": "神奈川・横須賀三浦", "pref": "kanagawa"},
    {"code": "kanagawa-central", "option": "県央", "label": "神奈川・県央", "pref": "kanagawa"},
    {"code": "kanagawa-shonan", "option": "湘南", "label": "神奈川・湘南", "pref": "kanagawa"},
    {"code": "kanagawa-west", "option": "県西", "label": "神奈川・県西", "pref": "kanagawa"},
    {"code": "saitama", "option": "埼玉", "label": "埼玉", "pref": "saitama"},
    {"code": "chiba", "option": "千葉", "label": "千葉", "pref": "chiba"},
    {"code": "ibaraki", "option": "茨城", "label": "茨城", "pref": "ibaraki"},
    {"code": "tochigi", "option": "栃木", "label": "栃木", "pref": "tochigi"},
    {"code": "gunma", "option": "群馬", "label": "群馬", "pref": "gunma"},
]

LEVELS = [
    ("beginner", "初心者中心"),
    ("enjoy", "エンジョイ"),
    ("mid", "中級"),
    ("strong", "しっかり"),
]

REPORT_REASONS = [
    ("spam", "スパム・宣伝"),
    ("scam", "詐欺っぽい・不審"),
    ("privacy", "個人情報の書き込み"),
    ("other", "その他"),
]

STATUSES = [
    ("open", "募集中"),
    ("closed", "募集終了"),
    ("all", "すべて"),
]

SORTS = [
    ("date_asc", "試合日が近い順"),
    ("date_desc", "試合日が遠い順"),
    ("updated", "最終更新が新しい順"),
]

POST_TYPE_MAP = {item["code"]: item for item in POST_TYPES}
LEVEL_MAP = dict(LEVELS)
REPORT_REASON_MAP = dict(REPORT_REASONS)
TIME_SLOT_MAP = dict(TIME_SLOTS)
PREF_MAP = dict(PREFECTURES)
AREA_MAP = {item["code"]: item for item in AREAS}
STATUS_MAP = dict(STATUSES)
SORT_MAP = dict(SORTS)

GROUPED_AREAS = []
_groups = {}
for pref_code, pref_label in PREFECTURES:
    group = {"code": pref_code, "label": pref_label, "areas": []}
    _groups[pref_code] = group
    GROUPED_AREAS.append(group)
for area in AREAS:
    _groups[area["pref"]]["areas"].append(area)
