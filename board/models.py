from datetime import datetime, timedelta

from flask_sqlalchemy import SQLAlchemy

from .constants import AREA_MAP, LEVEL_MAP, POST_TYPE_MAP, TIME_SLOT_MAP, WEEKDAYS

db = SQLAlchemy()


class Post(db.Model):
    __tablename__ = "posts"
    __table_args__ = (db.Index("ix_posts_status_date", "status", "event_date"),)

    id = db.Column(db.Integer, primary_key=True)
    post_type = db.Column(db.String(32), nullable=False, index=True)
    event_date = db.Column(db.Date, nullable=False, index=True)
    time_slot = db.Column(db.String(16), nullable=False)
    time_start = db.Column(db.Time, nullable=True)
    time_end = db.Column(db.Time, nullable=True)
    area = db.Column(db.String(32), nullable=False, index=True)
    place_detail = db.Column(db.String(120), nullable=False, default="")
    team_name = db.Column(db.String(80), nullable=False, default="")
    recruiter_name = db.Column(db.String(40), nullable=False, default="")
    level = db.Column(db.String(16), nullable=False, default="")
    headcount = db.Column(db.String(40), nullable=False, default="")
    positions = db.Column(db.String(80), nullable=False, default="")
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=False, default="")
    belongings = db.Column(db.Text, nullable=False, default="")
    fee = db.Column(db.String(80), nullable=False, default="")
    notes = db.Column(db.Text, nullable=False, default="")
    password_hash = db.Column(db.String(512), nullable=False)
    status = db.Column(db.String(16), nullable=False, default="open", index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    @property
    def type_label(self):
        return POST_TYPE_MAP[self.post_type]["label"]

    @property
    def type_short(self):
        return POST_TYPE_MAP[self.post_type]["short"]

    @property
    def area_label(self):
        return AREA_MAP[self.area]["label"]

    @property
    def weekday_label(self):
        return WEEKDAYS[self.event_date.weekday()]

    @property
    def time_label(self):
        if self.time_slot == "custom" and self.time_start and self.time_end:
            return f"{self.time_start.strftime('%H:%M')}–{self.time_end.strftime('%H:%M')}"
        return TIME_SLOT_MAP.get(self.time_slot, "")

    @property
    def date_label(self):
        day = self.event_date
        return f"{day.year}年{day.month}月{day.day}日（{self.weekday_label}）"

    @property
    def card_title(self):
        return self.team_name.strip() or self.type_label

    @property
    def status_label(self):
        return "募集中" if self.status == "open" else "募集終了"

    @property
    def level_label(self):
        return LEVEL_MAP.get(self.level, "")

    @property
    def fit_label(self):
        parts = [self.level_label, self.headcount.strip(), self.positions.strip()]
        return " · ".join(part for part in parts if part)

    @property
    def is_fresh(self):
        if self.status != "open" or self.updated_at is None:
            return False
        return self.updated_at >= datetime.now() - timedelta(hours=48)

    @property
    def updated_label(self):
        """一覧向けの短い最終更新表示。"""
        if self.updated_at is None:
            return ""
        now = datetime.now()
        stamp = self.updated_at
        delta = now - stamp
        if delta < timedelta(0):
            delta = timedelta(0)
        if delta < timedelta(minutes=1):
            return "更新 たった今"
        if delta < timedelta(hours=1):
            return f"更新 {int(delta.total_seconds() // 60)}分前"
        if stamp.date() == now.date():
            return f"更新 今日 {stamp.strftime('%H:%M')}"
        if stamp.date() == now.date() - timedelta(days=1):
            return f"更新 昨日 {stamp.strftime('%H:%M')}"
        if stamp.year == now.year:
            return f"更新 {stamp.month}/{stamp.day} {stamp.strftime('%H:%M')}"
        return f"更新 {stamp.year}/{stamp.month}/{stamp.day} {stamp.strftime('%H:%M')}"

    @property
    def prefecture_code(self):
        return AREA_MAP[self.area]["pref"]


class Report(db.Model):
    __tablename__ = "reports"

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    reason = db.Column(db.String(32), nullable=False)
    comment = db.Column(db.String(400), nullable=False, default="")
    ip = db.Column(db.String(64), nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    post = db.relationship("Post", backref=db.backref("reports", lazy=True, cascade="all, delete-orphan"))
