import base64
from datetime import date, datetime, timedelta

from sqlalchemy import inspect, text
from werkzeug.security import generate_password_hash

from .models import Post, db

DEMO_PASSWORD = "demo-pass"
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


def close_expired_posts():
    """試合日が昨日以前の募集中投稿を、募集終了にする。"""
    today = date.today()
    changed = (
        db.session.query(Post)
        .filter(Post.status == "open", Post.event_date < today)
        .update({"status": "closed"}, synchronize_session=False)
    )
    if changed:
        db.session.commit()
    else:
        db.session.rollback()
    return changed


def apply_cleaned(post, cleaned):
    for key in ASSIGNABLE:
        setattr(post, key, cleaned[key])
    if cleaned.get("password"):
        post.password_hash = generate_password_hash(cleaned["password"], method="pbkdf2:sha256")


def pack_secret(value):
    return base64.b64encode(value[::-1].encode("ascii")).decode("ascii")


def obfuscate_email(email):
    user, host = email.split("@", 1)
    return {"u": pack_secret(user), "h": pack_secret(host)}


def ensure_post_columns():
    """既存のSQLiteにも、あとから足した列を追加する。"""
    inspector = inspect(db.engine)
    if not inspector.has_table("posts"):
        return
    existing = {column["name"] for column in inspector.get_columns("posts")}
    additions = {
        "level": "VARCHAR(16) NOT NULL DEFAULT ''",
        "headcount": "VARCHAR(40) NOT NULL DEFAULT ''",
        "positions": "VARCHAR(80) NOT NULL DEFAULT ''",
        "phone": "VARCHAR(20) NOT NULL DEFAULT ''",
    }
    for name, column_type in additions.items():
        if name not in existing:
            db.session.execute(text(f"ALTER TABLE posts ADD COLUMN {name} {column_type}"))
    db.session.commit()


def form_from_post(post):
    return {
        "post_type": post.post_type,
        "event_date": post.event_date.isoformat(),
        "time_slot": post.time_slot,
        "time_start": post.time_start.strftime("%H:%M") if post.time_start else "",
        "time_end": post.time_end.strftime("%H:%M") if post.time_end else "",
        "area": post.area,
        "place_detail": post.place_detail,
        "team_name": post.team_name,
        "recruiter_name": post.recruiter_name,
        "level": post.level,
        "headcount": post.headcount,
        "positions": post.positions,
        "email": post.email,
        "phone": post.phone,
        "fee": post.fee,
        "belongings": post.belongings,
        "notes": post.notes,
        "password": "",
        "password_confirm": "",
        "new_password": "",
        "new_password_confirm": "",
    }


def empty_form():
    return {
        "post_type": "",
        "event_date": "",
        "time_slot": "morning",
        "time_start": "",
        "time_end": "",
        "area": "",
        "place_detail": "",
        "team_name": "",
        "recruiter_name": "",
        "level": "",
        "headcount": "",
        "positions": "",
        "email": "",
        "phone": "",
        "fee": "",
        "belongings": "",
        "notes": "",
        "password": "",
        "password_confirm": "",
        "new_password": "",
        "new_password_confirm": "",
    }


def seed_posts():
    if db.session.query(Post.id).first():
        return
    today = date.today()
    password_hash = generate_password_hash(DEMO_PASSWORD, method="pbkdf2:sha256")
    now = datetime.now()
    samples = [
        dict(
            post_type="helper",
            event_date=today + timedelta(days=3),
            time_slot="afternoon",
            area="saitama",
            place_detail="さいたま市岩槻総合公園",
            team_name="大宮サンダース",
            recruiter_name="佐藤",
            level="enjoy",
            headcount="あと2人",
            positions="遊撃、捕手",
            email="sato@example.com",
            fee="無料",
            belongings="グローブ、スパイク",
            notes="ショートとキャッチャーを1人ずつ探しています。13時半グラウンド集合、16時終了予定です。",
        ),
        dict(
            post_type="with_ground",
            event_date=today + timedelta(days=6),
            time_slot="morning",
            area="tokyo-23",
            place_detail="江戸川区臨海球技場",
            team_name="江戸川リバーズ",
            recruiter_name="田中",
            level="enjoy",
            headcount="12〜15人",
            positions="一通りそろう相手",
            email="tanaka@example.com",
            fee="グラウンド代割り勘（1人1,000円目安）",
            belongings="ユニフォーム、グローブ、スパイク",
            notes="9時半集合、13時終了予定です。エンジョイ寄りですが、守備位置が一通りそろうチームを希望します。",
        ),
        dict(
            post_type="without_ground",
            event_date=today + timedelta(days=12),
            time_slot="custom",
            time_start=datetime.strptime("09:00", "%H:%M").time(),
            time_end=datetime.strptime("12:00", "%H:%M").time(),
            area="kanagawa-yokohama",
            place_detail="横浜市内。グラウンドは相手チーム側で確保できる方を探しています",
            team_name="横浜ベイ",
            recruiter_name="鈴木",
            level="mid",
            headcount="13人前後",
            email="suzuki@example.com",
            fee="グラウンド代は折半で相談",
            belongings="ユニフォーム上下、グローブ",
            notes="グラウンドを持っていないため、会場を用意できるチームの相手を探しています。レベルは中級です。",
        ),
        dict(
            post_type="with_ground",
            event_date=today + timedelta(days=20),
            time_slot="night",
            area="kanagawa-shonan",
            place_detail="平塚市総合公園野球場",
            team_name="湘南ブルーウェーブ",
            recruiter_name="高橋",
            level="enjoy",
            headcount="10人以上",
            email="takahashi@example.com",
            fee="1人800円",
            belongings="ナイター対応の服装、グローブ",
            notes="照明ありのナイターです。18時15分集合、21時頃終了予定。雨天中止の連絡は前日夜までにします。",
        ),
        dict(
            post_type="without_ground",
            event_date=today + timedelta(days=6),
            time_slot="morning",
            area="tokyo-23",
            place_detail="東京23区内。グラウンドは相手チームを希望",
            team_name="城東ウォリアーズ",
            recruiter_name="小林",
            level="mid",
            headcount="14人",
            email="guest@example.com",
            fee="グラウンド代は折半で相談",
            belongings="ユニフォーム、グローブ",
            notes="グラウンドを持っていないので、会場があるチームと練習試合がしたいです。",
        ),
        dict(
            post_type="with_ground",
            event_date=today - timedelta(days=2),
            time_slot="morning",
            area="tokyo-tama",
            place_detail="府中市民球場",
            team_name="多摩クラウンズ",
            recruiter_name="伊藤",
            email="ito@example.com",
            fee="1人1,200円",
            belongings="ユニフォーム、グローブ",
            notes="この投稿は試合日を過ぎているサンプルです。一覧では募集終了になります。",
        ),
    ]
    for item in samples:
        db.session.add(
            Post(
                password_hash=password_hash,
                status="open",
                created_at=now,
                updated_at=now,
                place_detail=item.get("place_detail", ""),
                team_name=item.get("team_name", ""),
                recruiter_name=item.get("recruiter_name", ""),
                belongings=item.get("belongings", ""),
                fee=item.get("fee", ""),
                notes=item.get("notes", ""),
                level=item.get("level", ""),
                headcount=item.get("headcount", ""),
                positions=item.get("positions", ""),
                phone=item.get("phone", ""),
                time_start=item.get("time_start"),
                time_end=item.get("time_end"),
                post_type=item["post_type"],
                event_date=item["event_date"],
                time_slot=item["time_slot"],
                area=item["area"],
                email=item["email"],
            )
        )
    db.session.commit()


SAMPLE_DETAILS = {
    "sato@example.com": {
        "team_name": "大宮サンダース",
        "level": "enjoy",
        "headcount": "あと2人",
        "positions": "遊撃、捕手",
    },
    "tanaka@example.com": {
        "team_name": "江戸川リバーズ",
        "level": "enjoy",
        "headcount": "12〜15人",
        "positions": "一通りそろう相手",
    },
    "suzuki@example.com": {
        "team_name": "横浜ベイ",
        "level": "mid",
        "headcount": "13人前後",
        "positions": "",
    },
    "takahashi@example.com": {
        "team_name": "湘南ブルーウェーブ",
        "level": "enjoy",
        "headcount": "10人以上",
        "positions": "",
    },
}


def backfill_sample_details():
    """サンプル投稿に、あとから足した項目だけを埋める。"""
    changed = False
    for email, extra in SAMPLE_DETAILS.items():
        post = (
            db.session.query(Post)
            .filter(Post.email == email, Post.team_name == extra["team_name"], Post.level == "")
            .first()
        )
        if post is None:
            continue
        post.level = extra["level"]
        post.headcount = extra["headcount"]
        post.positions = extra["positions"]
        changed = True
    if changed:
        db.session.commit()
    else:
        db.session.rollback()


def clear_stored_phones():
    """電話連絡をやめたので、保存済みの番号を空にする。"""
    changed = (
        db.session.query(Post)
        .filter(Post.phone != "")
        .update({"phone": ""}, synchronize_session=False)
    )
    if changed:
        db.session.commit()
    else:
        db.session.rollback()
    return changed


def ensure_counterpart_sample():
    """グラウンドありのサンプルと同じ日に、グラウンドなしの相手候補を1件置く。"""
    host = (
        db.session.query(Post)
        .filter(Post.team_name == "江戸川リバーズ", Post.email == "tanaka@example.com")
        .first()
    )
    if host is None:
        return
    exists = (
        db.session.query(Post.id)
        .filter(Post.team_name == "城東ウォリアーズ", Post.email == "guest@example.com")
        .first()
    )
    if exists is not None:
        return
    now = datetime.now()
    db.session.add(
        Post(
            post_type="without_ground",
            event_date=host.event_date,
            time_slot="morning",
            area="tokyo-23",
            place_detail="東京23区内。グラウンドは相手チームを希望",
            team_name="城東ウォリアーズ",
            recruiter_name="小林",
            level="mid",
            headcount="14人",
            email="guest@example.com",
            fee="グラウンド代は折半で相談",
            belongings="ユニフォーム、グローブ",
            notes="グラウンドを持っていないので、会場があるチームと練習試合がしたいです。",
            password_hash=generate_password_hash(DEMO_PASSWORD, method="pbkdf2:sha256"),
            status="open" if host.event_date >= date.today() else "closed",
            created_at=now,
            updated_at=now,
        )
    )
    db.session.commit()
