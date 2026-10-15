from datetime import date, datetime, time, timedelta
from urllib.parse import quote

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for
from sqlalchemy import extract, func, or_
from werkzeug.security import check_password_hash

from .constants import (
    AREA_MAP,
    LEVEL_MAP,
    POST_TYPE_MAP,
    PREF_MAP,
    REPORT_REASON_MAP,
    SORT_MAP,
    STATUS_MAP,
    WEEKDAYS,
)
from .models import Post, Report, db
from .security import (
    allow_manage,
    can_manage,
    clear_failures,
    forget_manage,
    rate_limited,
    record_failure,
    record_report,
    report_rate_limited,
)
from .holidays import holiday_dates_between
from .services import apply_cleaned, empty_form, form_from_post, obfuscate_email
from .validation import validate_post_form

bp = Blueprint("main", __name__)

PER_PAGE = 20
FORM_KEYS = (
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
    "fee",
    "belongings",
    "notes",
    "password",
    "password_confirm",
    "new_password",
    "new_password_confirm",
)

SLOT_STARTS = {
    "morning": time(9, 0),
    "afternoon": time(13, 0),
    "night": time(18, 0),
    "allday": time(9, 0),
}
SLOT_ENDS = {
    "morning": time(12, 0),
    "afternoon": time(17, 0),
    "night": time(21, 0),
    "allday": time(17, 0),
}


class Page:
    def __init__(self, items, page, per_page, total):
        self.items = items
        self.page = page
        self.per_page = per_page
        self.total = total
        self.pages = max((total + per_page - 1) // per_page, 1) if total else 1
        self.has_prev = page > 1
        self.has_next = page < self.pages


def raw_form():
    return {key: request.form.get(key, "") for key in FORM_KEYS}


def clear_secret_fields(raw):
    for key in ("password", "password_confirm", "new_password", "new_password_confirm"):
        raw[key] = ""
    return raw


def get_post_or_404(post_id):
    post = db.session.get(Post, post_id)
    if post is None:
        abort(404)
    return post


def parse_on(value):
    try:
        return date.fromisoformat((value or "").strip())
    except ValueError:
        return None


def as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def like_pattern(keyword):
    escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def apply_keyword(query, keyword):
    pattern = like_pattern(keyword)
    columns = (
        Post.team_name,
        Post.place_detail,
        Post.notes,
        Post.positions,
        Post.headcount,
        Post.recruiter_name,
        Post.belongings,
    )
    return query.filter(or_(*(column.like(pattern, escape="\\") for column in columns)))


def apply_weekend_or_holiday(query):
    """土曜・日曜・祝日の試合日に限定する。"""
    today = date.today()
    holidays = holiday_dates_between(today - timedelta(days=400), today + timedelta(days=400))
    dialect = db.engine.dialect.name
    if dialect == "sqlite":
        weekend = func.strftime("%w", Post.event_date).in_(("0", "6"))
    else:
        weekend = extract("dow", Post.event_date).in_((0, 6))
    if holidays:
        return query.filter(or_(weekend, Post.event_date.in_(holidays)))
    return query.filter(weekend)


def find_similar_posts(cleaned, exclude_id=None):
    query = db.session.query(Post).filter(
        Post.status == "open",
        Post.event_date == cleaned["event_date"],
        Post.area == cleaned["area"],
        Post.post_type == cleaned["post_type"],
    )
    if exclude_id is not None:
        query = query.filter(Post.id != exclude_id)
    return query.order_by(Post.updated_at.desc(), Post.id.desc()).limit(8).all()


def prefer_same_pref(posts, pref_code):
    return sorted(
        posts,
        key=lambda item: (
            0 if AREA_MAP[item.area]["pref"] == pref_code else 1,
            -(item.updated_at.timestamp() if item.updated_at else 0),
            -item.id,
        ),
    )


def event_bounds(post):
    if post.time_slot == "custom" and post.time_start and post.time_end:
        return post.time_start, post.time_end
    start = SLOT_STARTS.get(post.time_slot, time(9, 0))
    end = SLOT_ENDS.get(post.time_slot, time(12, 0))
    return start, end


def build_ics(post):
    start_t, end_t = event_bounds(post)
    start = datetime.combine(post.event_date, start_t)
    end = datetime.combine(post.event_date, end_t)
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    uid = f"post-{post.id}@baseball-message-board"
    summary = post.card_title.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;")
    description = " \\n".join(
        part.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;")
        for part in (
            post.type_label,
            post.time_label,
            post.fit_label,
            post.notes.strip()[:200],
        )
        if part
    )
    location = " ".join(part for part in (post.area_label, post.place_detail.strip()) if part)
    location = location.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//草野球ボード//JP",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{stamp}",
        f"DTSTART:{start.strftime('%Y%m%dT%H%M%S')}",
        f"DTEND:{end.strftime('%Y%m%dT%H%M%S')}",
        f"SUMMARY:{summary}",
        f"DESCRIPTION:{description}",
        f"LOCATION:{location}",
        "END:VEVENT",
        "END:VCALENDAR",
        "",
    ]
    return "\r\n".join(lines)


COUNTERPARTS = {"with_ground": "without_ground", "without_ground": "with_ground"}
COUNTERPART_LABELS = {
    "with_ground": "この日、グラウンドを探しているチーム",
    "without_ground": "この日、グラウンドがあるチーム",
}


@bp.get("/")
def index():
    status = request.args.get("status", "open")
    if status not in STATUS_MAP:
        status = "open"

    post_type = request.args.get("post_type", "")
    if post_type not in POST_TYPE_MAP:
        post_type = ""

    area = request.args.get("area", "")
    if area not in AREA_MAP:
        area = ""

    prefecture = request.args.get("prefecture", "")
    if prefecture not in PREF_MAP:
        prefecture = ""
    if area:
        prefecture = AREA_MAP[area]["pref"]

    level = request.args.get("level", "")
    if level not in LEVEL_MAP:
        level = ""

    weekend = request.args.get("weekend", "") == "1"

    sort = request.args.get("sort", "")
    if sort not in SORT_MAP:
        sort = "date_desc" if status == "closed" else "date_asc"

    keyword = " ".join((request.args.get("q") or "").split())[:40]
    on_date = parse_on(request.args.get("on"))

    query = db.session.query(Post)
    if status != "all":
        query = query.filter(Post.status == status)
    if area:
        query = query.filter(Post.area == area)
    elif prefecture:
        codes = [item["code"] for item in AREA_MAP.values() if item["pref"] == prefecture]
        query = query.filter(Post.area.in_(codes))
    if post_type:
        query = query.filter(Post.post_type == post_type)
    if level:
        query = query.filter(Post.level == level)
    if weekend:
        query = apply_weekend_or_holiday(query)
    if keyword:
        query = apply_keyword(query, keyword)

    rail = []
    if status != "closed":
        today = date.today()
        days = [today + timedelta(days=offset) for offset in range(14)]
        counted = (
            query.filter(Post.status == "open", Post.event_date >= days[0], Post.event_date <= days[-1])
            .with_entities(Post.event_date, func.count())
            .group_by(Post.event_date)
            .all()
        )
        counts = {as_date(event_date): count for event_date, count in counted}
        rail = [
            {
                "iso": day.isoformat(),
                "md": f"{day.month}/{day.day}",
                "weekday": WEEKDAYS[day.weekday()],
                "dow": day.weekday(),
                "count": counts.get(day, 0),
                "is_today": day == today,
            }
            for day in days
        ]

    if on_date:
        query = query.filter(Post.event_date == on_date)

    if sort == "updated":
        query = query.order_by(Post.updated_at.desc(), Post.id.desc())
    elif sort == "date_desc":
        query = query.order_by(Post.event_date.desc(), Post.id.desc())
    else:
        query = query.order_by(Post.event_date.asc(), Post.id.asc())

    total = query.count()
    pages = max((total + PER_PAGE - 1) // PER_PAGE, 1) if total else 1
    page_num = request.args.get("page", 1, type=int) or 1
    if page_num < 1:
        page_num = 1
    if page_num > pages:
        page_num = pages
    items = query.offset((page_num - 1) * PER_PAGE).limit(PER_PAGE).all()
    page = Page(items, page_num, PER_PAGE, total)

    params = {"status": status, "sort": sort}
    if post_type:
        params["post_type"] = post_type
    if prefecture:
        params["prefecture"] = prefecture
    if area:
        params["area"] = area
    if level:
        params["level"] = level
    if weekend:
        params["weekend"] = "1"
    if keyword:
        params["q"] = keyword
    if on_date:
        params["on"] = on_date.isoformat()

    def build_url(**overrides):
        merged = dict(params)
        for key, value in overrides.items():
            if value in (None, ""):
                merged.pop(key, None)
            else:
                merged[key] = value
        return url_for("main.index", **merged)

    def page_url(number):
        return url_for("main.index", page=number, **params)

    status_label = {"open": "募集中", "closed": "募集終了", "all": "すべての投稿"}[status]
    if area:
        heading = f"{AREA_MAP[area]['label']}の{status_label}"
    elif prefecture:
        heading = f"{PREF_MAP[prefecture]}の{status_label}"
    else:
        heading = status_label
    if post_type:
        heading = f"{heading}（{POST_TYPE_MAP[post_type]['short']}）"
    if level:
        heading = f"{heading}（{LEVEL_MAP[level]}）"
    if weekend:
        heading = f"土日祝の{heading}"
    if on_date:
        heading = f"{on_date.month}月{on_date.day}日（{WEEKDAYS[on_date.weekday()]}）の{heading}"
    if keyword:
        heading = f"{heading}「{keyword}」"

    has_any = db.session.query(Post.id).first() is not None
    return render_template(
        "index.html",
        posts=page.items,
        page=page,
        status=status,
        post_type=post_type,
        prefecture=prefecture,
        area=area,
        level=level,
        weekend=weekend,
        sort=sort,
        keyword=keyword,
        on=on_date.isoformat() if on_date else "",
        date_rail=rail,
        heading=heading,
        has_any=has_any,
        build_url=build_url,
        page_url=page_url,
    )


@bp.get("/guide")
def guide():
    return render_template("guide.html")


@bp.route("/posts/new", methods=["GET", "POST"])
def create_post():
    form = empty_form()
    errors = []
    similar_posts = []
    if request.method == "POST":
        form = raw_form()
        cleaned, errors = validate_post_form(form, creating=True, today=date.today())
        if not errors:
            similar_posts = find_similar_posts(cleaned)
            confirmed = request.form.get("confirm_similar") == "1"
            if similar_posts and not confirmed:
                return render_template(
                    "form.html",
                    form=form,
                    errors=errors,
                    similar_posts=similar_posts,
                    date_min=date.today().isoformat(),
                )
            post = Post(status="open", password_hash="pending")
            apply_cleaned(post, cleaned)
            post.updated_at = datetime.now()
            db.session.add(post)
            db.session.commit()
            allow_manage(post.id)
            flash("投稿しました。暗証番号は、この投稿の編集・終了・削除に使います。", "success")
            return redirect(url_for("main.post_detail", post_id=post.id))
        clear_secret_fields(form)
    return render_template(
        "form.html",
        form=form,
        errors=errors,
        similar_posts=similar_posts,
        date_min=date.today().isoformat(),
    )


@bp.get("/posts/<int:post_id>")
def post_detail(post_id):
    post = get_post_or_404(post_id)
    subject = f"【草野球ボード】{post.date_label} {post.area_label}の件"
    counterparts = []
    same_day = []
    if post.event_date >= date.today():
        others = (
            db.session.query(Post)
            .filter(Post.id != post.id, Post.status == "open", Post.event_date == post.event_date)
            .order_by(Post.updated_at.desc(), Post.id.desc())
            .limit(24)
            .all()
        )
        wanted = COUNTERPARTS.get(post.post_type)
        pref = post.prefecture_code
        counterparts = prefer_same_pref([item for item in others if item.post_type == wanted], pref)[:10]
        same_day = prefer_same_pref([item for item in others if item.post_type != wanted], pref)[:8]
    maps_url = ""
    if post.place_detail.strip():
        maps_url = "https://www.google.com/maps/search/?api=1&query=" + quote(
            f"{post.area_label} {post.place_detail.strip()}"
        )
    share = {
        "title": post.card_title,
        "text": "\n".join(
            line
            for line in (
                f"{post.date_label} {post.time_label}",
                post.type_label,
                " / ".join(part for part in (post.team_name.strip(), post.area_label) if part),
                post.place_detail.strip(),
                post.fit_label,
            )
            if line
        ),
        "url": url_for("main.post_detail", post_id=post.id, _external=True),
    }
    return render_template(
        "detail.html",
        post=post,
        mail=obfuscate_email(post.email),
        subject=subject,
        unlocked=can_manage(post.id),
        counterparts=counterparts,
        counterpart_label=COUNTERPART_LABELS.get(post.post_type, ""),
        same_day=same_day,
        maps_url=maps_url,
        share=share,
    )


@bp.get("/posts/<int:post_id>.ics")
def post_ics(post_id):
    post = get_post_or_404(post_id)
    body = build_ics(post)
    filename = f"post-{post.id}.ics"
    return Response(
        body.encode("utf-8"),
        mimetype="text/calendar",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "text/calendar; charset=utf-8",
        },
    )


@bp.route("/posts/<int:post_id>/report", methods=["GET", "POST"])
def report_post(post_id):
    post = get_post_or_404(post_id)
    errors = []
    reason = ""
    comment = ""
    if request.method == "POST":
        if report_rate_limited(post.id):
            flash("通報が多すぎます。しばらく待ってからもう一度お試しください。", "error")
            return redirect(url_for("main.post_detail", post_id=post.id))
        reason = (request.form.get("reason") or "").strip()
        comment = " ".join((request.form.get("comment") or "").split())[:400]
        if reason not in REPORT_REASON_MAP:
            errors.append("通報の理由を選んでください。")
        if not errors:
            report = Report(
                post_id=post.id,
                reason=reason,
                comment=comment,
                ip=(request.remote_addr or "")[:64],
            )
            db.session.add(report)
            db.session.commit()
            record_report(post.id)
            flash("通報を受け付けました。ご協力ありがとうございます。", "success")
            return redirect(url_for("main.post_detail", post_id=post.id))
    return render_template(
        "report.html",
        post=post,
        errors=errors,
        reason=reason,
        comment=comment,
    )


@bp.route("/posts/<int:post_id>/manage", methods=["GET", "POST"])
def manage_post(post_id):
    post = get_post_or_404(post_id)
    errors = []
    form = form_from_post(post)

    if request.method == "POST":
        action = request.form.get("action", "")
        if action == "unlock":
            return _unlock(post)
        if not can_manage(post.id):
            flash("先に暗証番号を入力してください。", "error")
            return redirect(url_for("main.manage_post", post_id=post.id))
        if action == "update":
            form = raw_form()
            cleaned, errors = validate_post_form(form, creating=False, today=date.today())
            if not errors:
                apply_cleaned(post, cleaned)
                if post.event_date < date.today():
                    post.status = "closed"
                post.updated_at = datetime.now()
                db.session.commit()
                flash("投稿を更新しました。", "success")
                return redirect(url_for("main.post_detail", post_id=post.id))
            clear_secret_fields(form)
        elif action == "close":
            if post.status != "closed":
                post.status = "closed"
                post.updated_at = datetime.now()
                db.session.commit()
            flash("募集を終了しました。", "success")
            return redirect(url_for("main.post_detail", post_id=post.id))
        elif action == "reopen":
            if post.event_date < date.today():
                flash("試合日を過ぎているため、募集中に戻せません。日付を今日以降に変更してください。", "error")
            elif post.status == "open":
                flash("すでに募集中です。", "info")
            else:
                post.status = "open"
                post.updated_at = datetime.now()
                db.session.commit()
                flash("募集中に戻しました。", "success")
            return redirect(url_for("main.manage_post", post_id=post.id))
        elif action == "delete":
            db.session.query(Report).filter_by(post_id=post.id).delete()
            db.session.delete(post)
            db.session.commit()
            forget_manage(post_id)
            flash("投稿を削除しました。", "success")
            return redirect(url_for("main.index"))
        else:
            abort(400)

    return render_template(
        "manage.html",
        post=post,
        form=form,
        errors=errors,
        unlocked=can_manage(post.id),
    )


def _unlock(post):
    if rate_limited(post.id):
        flash("試行が多すぎます。10分ほど待ってからもう一度お試しください。", "error")
        return render_template(
            "manage.html",
            post=post,
            form=form_from_post(post),
            errors=[],
            unlocked=False,
        )
    password = (request.form.get("password") or "").strip()
    if password and check_password_hash(post.password_hash, password):
        clear_failures(post.id)
        allow_manage(post.id)
        flash("暗証番号を確認しました。", "success")
        return redirect(url_for("main.manage_post", post_id=post.id))
    record_failure(post.id)
    flash("暗証番号が違います。", "error")
    return render_template(
        "manage.html",
        post=post,
        form=form_from_post(post),
        errors=[],
        unlocked=False,
    )
