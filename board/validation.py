import re
from datetime import date, datetime, timedelta

from .constants import AREA_MAP, LEVEL_MAP, POST_TYPE_MAP, TIME_SLOT_MAP

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

ASSIGNABLE = (
    "post_type",
    "event_date",
    "time_slot",
    "time_start",
    "time_end",
    "area",
    "place_detail",
    "team_name",
    "recruiter_name",
    "level",
    "headcount",
    "positions",
    "email",
    "phone",
    "fee",
    "belongings",
    "notes",
)


def clean_line(value, limit):
    text = CONTROL_CHARS.sub("", (value or "").replace("\r", "").replace("\n", " ")).strip()
    return text, len(text) > limit


def clean_multiline(value, limit):
    text = CONTROL_CHARS.sub("", (value or "").replace("\r\n", "\n").replace("\r", "\n")).strip()
    return text, len(text) > limit


def parse_time(value):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError:
        return None


def validate_post_form(raw, *, creating, today):
    errors = []
    post_type = (raw.get("post_type") or "").strip()
    if post_type not in POST_TYPE_MAP:
        errors.append("募集タイプを選択してください。")

    event_raw = (raw.get("event_date") or "").strip()
    event_date = None
    try:
        event_date = date.fromisoformat(event_raw)
    except ValueError:
        errors.append("試合日を入力してください。")
    else:
        if event_date > today + timedelta(days=365):
            errors.append("試合日は今日から1年以内で指定してください。")
        elif creating and event_date < today:
            errors.append("試合日は今日以降を指定してください。")

    time_slot = (raw.get("time_slot") or "").strip()
    time_start = None
    time_end = None
    if time_slot not in TIME_SLOT_MAP:
        errors.append("時間帯を選択してください。")
    elif time_slot == "custom":
        time_start = parse_time(raw.get("time_start"))
        time_end = parse_time(raw.get("time_end"))
        if time_start is None or time_end is None:
            errors.append("開始時刻と終了時刻を入力してください。")
        elif time_start >= time_end:
            errors.append("終了時刻は開始時刻より後にしてください。")

    area = (raw.get("area") or "").strip()
    if area not in AREA_MAP:
        errors.append("場所を選択してください。")

    place_detail, place_over = clean_line(raw.get("place_detail"), 120)
    team_name, team_over = clean_line(raw.get("team_name"), 80)
    recruiter_name, name_over = clean_line(raw.get("recruiter_name"), 40)
    level = (raw.get("level") or "").strip()
    headcount, headcount_over = clean_line(raw.get("headcount"), 40)
    positions, positions_over = clean_line(raw.get("positions"), 80)
    fee, fee_over = clean_line(raw.get("fee"), 80)
    belongings, belongings_over = clean_multiline(raw.get("belongings"), 500)
    notes, notes_over = clean_multiline(raw.get("notes"), 2000)
    if place_over:
        errors.append("グラウンド名・集合場所は120文字以内で入力してください。")
    if team_over:
        errors.append("チーム名は80文字以内で入力してください。")
    if name_over:
        errors.append("募集者名は40文字以内で入力してください。")
    if level and level not in LEVEL_MAP:
        errors.append("レベルを選択し直してください。")
    if headcount_over:
        errors.append("人数の目安は40文字以内で入力してください。")
    if positions_over:
        errors.append("欲しいポジションは80文字以内で入力してください。")
    if fee_over:
        errors.append("参加費は80文字以内で入力してください。")
    if belongings_over:
        errors.append("持ち物は500文字以内で入力してください。")
    if notes_over:
        errors.append("留意事項は2000文字以内で入力してください。")

    email = (raw.get("email") or "").strip().lower()
    if not EMAIL_RE.fullmatch(email) or len(email) > 120:
        errors.append("連絡先メールアドレスの形式を確認してください。")

    password_value = None
    if creating:
        password = (raw.get("password") or "").strip()
        confirm = (raw.get("password_confirm") or "").strip()
        if len(password) < 4:
            errors.append("暗証番号は4文字以上で設定してください。")
        elif len(password) > 64:
            errors.append("暗証番号は64文字以内で設定してください。")
        elif password != confirm:
            errors.append("暗証番号（確認）が一致しません。")
        else:
            password_value = password
    else:
        new_password = (raw.get("new_password") or "").strip()
        new_confirm = (raw.get("new_password_confirm") or "").strip()
        if new_password or new_confirm:
            if len(new_password) < 4:
                errors.append("新しい暗証番号は4文字以上で設定してください。")
            elif len(new_password) > 64:
                errors.append("新しい暗証番号は64文字以内で設定してください。")
            elif new_password != new_confirm:
                errors.append("新しい暗証番号が一致しません。")
            else:
                password_value = new_password

    if errors:
        return None, errors

    cleaned = {
        "post_type": post_type,
        "event_date": event_date,
        "time_slot": time_slot,
        "time_start": time_start if time_slot == "custom" else None,
        "time_end": time_end if time_slot == "custom" else None,
        "area": area,
        "place_detail": place_detail,
        "team_name": team_name,
        "recruiter_name": recruiter_name,
        "level": level,
        "headcount": headcount,
        "positions": positions,
        "email": email,
        "phone": "",
        "fee": fee,
        "belongings": belongings,
        "notes": notes,
        "password": password_value,
    }
    return cleaned, []
