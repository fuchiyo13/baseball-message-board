import os
import secrets
from datetime import date, timedelta
from pathlib import Path

from flask import Flask, render_template, request
from werkzeug.exceptions import HTTPException

from .constants import (
    GROUPED_AREAS,
    LEVELS,
    POST_TYPES,
    PREFECTURES,
    REPORT_REASONS,
    SORTS,
    TIME_SLOTS,
    WEEKDAYS,
)
from .models import db
from .security import ensure_csrf, verify_csrf

ROOT = Path(__file__).resolve().parent.parent


def create_app(test_config=None):
    test_config = dict(test_config or {})
    app = Flask(
        __name__,
        root_path=str(ROOT),
        instance_path=str(ROOT / "instance"),
    )
    app.config.from_mapping(
        SECRET_KEY="dev",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        MAX_CONTENT_LENGTH=256 * 1024,
        TESTING=False,
        JSON_AS_ASCII=False,
    )

    testing = bool(test_config.get("TESTING"))
    if "SECRET_KEY" in test_config:
        app.config["SECRET_KEY"] = test_config.pop("SECRET_KEY")
    elif not testing:
        app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or _load_secret_key(Path(app.instance_path))

    uri = test_config.pop("SQLALCHEMY_DATABASE_URI", None)
    if uri is None:
        if testing:
            uri = "sqlite:///:memory:"
        else:
            Path(app.instance_path).mkdir(parents=True, exist_ok=True)
            env_uri = os.environ.get("DATABASE_URL")
            if env_uri:
                uri = _normalize_database_url(env_uri)
            else:
                db_path = Path(app.instance_path) / "board.db"
                uri = "sqlite:///" + db_path.as_posix()
    else:
        uri = _normalize_database_url(uri)
    app.config["SQLALCHEMY_DATABASE_URI"] = uri
    app.config.update(test_config)

    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"connect_args": {"check_same_thread": False}}
    else:
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}

    db.init_app(app)
    from .routes import bp

    app.register_blueprint(bp)
    _register_hooks(app)

    with app.app_context():
        db.create_all()
        from .services import ensure_post_columns

        ensure_post_columns()
        if not app.config.get("TESTING"):
            from .services import clear_stored_phones

            clear_stored_phones()
            # 本番では空のまま起動する。デモ用サンプルが必要なときだけ SEED_SAMPLE=1
            if os.environ.get("SEED_SAMPLE") == "1":
                from .services import (
                    backfill_sample_details,
                    ensure_counterpart_sample,
                    seed_posts,
                )

                seed_posts()
                backfill_sample_details()
                ensure_counterpart_sample()
        from .services import close_expired_posts

        close_expired_posts()
    return app


def _load_secret_key(instance_path):
    instance_path.mkdir(parents=True, exist_ok=True)
    path = instance_path / "secret_key"
    if path.exists():
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    key = secrets.token_hex(32)
    path.write_text(key, encoding="utf-8")
    return key


def _normalize_database_url(url):
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://") :]
    return url


def _register_hooks(app):
    @app.before_request
    def _csrf():
        verify_csrf()

    @app.before_request
    def _cleanup():
        if request.endpoint == "static":
            return
        from .services import close_expired_posts

        close_expired_posts()

    @app.after_request
    def _headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    @app.context_processor
    def _inject():
        today = date.today()
        return {
            "csrf_token": ensure_csrf,
            "today": today,
            "max_date": (today + timedelta(days=365)).isoformat(),
            "grouped_areas": GROUPED_AREAS,
            "post_types": POST_TYPES,
            "levels": LEVELS,
            "report_reasons": REPORT_REASONS,
            "time_slots": TIME_SLOTS,
            "prefectures": PREFECTURES,
            "sorts": SORTS,
        }

    @app.template_filter("weekday_of")
    def weekday_of(value):
        try:
            parsed = date.fromisoformat(value or "")
        except ValueError:
            return "—"
        return WEEKDAYS[parsed.weekday()] + "曜日"

    @app.errorhandler(HTTPException)
    def _http_error(error):
        messages = {
            400: "送信を確認できませんでした。ページを再読み込みして、もう一度操作してください。",
            403: "この操作はできません。",
            404: "ページが見つかりません。削除された投稿か、アドレスが違う可能性があります。",
        }
        message = messages.get(error.code, "処理できませんでした。")
        titles = {400: "送信エラー", 403: "操作できません", 404: "見つかりません"}
        return render_template("error.html", title=titles.get(error.code, "エラー"), message=message), error.code
