import base64
import os
import re
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse

from werkzeug.security import generate_password_hash

from board import create_app
from board.models import Post, Report, db
from board.routes import PER_PAGE
from board.security import reset_rate_limit


class BoardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fd, cls.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        cls.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret",
                "SQLALCHEMY_DATABASE_URI": "sqlite:///" + Path(cls.db_path).as_posix(),
                "TRAP_HTTP_EXCEPTIONS": False,
                "PROPAGATE_EXCEPTIONS": False,
            }
        )
        cls.password_hash = generate_password_hash("secret12", method="pbkdf2:sha256")

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            db.engine.dispose()
        os.unlink(cls.db_path)

    def setUp(self):
        self.client = self.app.test_client()
        reset_rate_limit()
        with self.app.app_context():
            db.session.query(Report).delete()
            db.session.query(Post).delete()
            db.session.commit()

    def next_weekday(self, weekday):
        day = date.today()
        while day.weekday() != weekday:
            day += timedelta(days=1)
        return day

    def make_post(self, **kwargs):
        data = {
            "post_type": "helper",
            "event_date": date.today() + timedelta(days=3),
            "time_slot": "morning",
            "area": "tokyo-23",
            "email": "tester@example.com",
            "password_hash": self.password_hash,
            "team_name": "テスト球団",
            "status": "open",
        }
        data.update(kwargs)
        with self.app.app_context():
            post = Post(**data)
            db.session.add(post)
            db.session.commit()
            return post.id

    def csrf_from(self, response):
        html = response.get_data(as_text=True)
        match = re.search(r'name="csrf_token" value="([^"]+)"', html)
        self.assertIsNotNone(match)
        return match.group(1)

    def payload(self, token, **overrides):
        data = {
            "csrf_token": token,
            "post_type": "with_ground",
            "event_date": (date.today() + timedelta(days=5)).isoformat(),
            "time_slot": "morning",
            "time_start": "",
            "time_end": "",
            "area": "tokyo-23",
            "place_detail": "試験グラウンド",
            "team_name": "テスト球団",
            "recruiter_name": "山田",
            "email": "captain@example.com",
            "fee": "500円",
            "belongings": "グローブ",
            "notes": "集合は開始30分前です。",
            "password": "secret12",
            "password_confirm": "secret12",
        }
        data.update(overrides)
        return data

    def test_empty_index(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("まだ募集はありません", html)
        self.assertIn("曜日", self.client.get("/posts/new").get_data(as_text=True))

    def test_past_post_is_closed_and_hidden_from_open_list(self):
        past_id = self.make_post(team_name="昨日の試合", event_date=date.today() - timedelta(days=1))
        self.make_post(team_name="今日の試合", event_date=date.today())
        open_html = self.client.get("/").get_data(as_text=True)
        self.assertIn("今日の試合", open_html)
        self.assertNotIn("昨日の試合", open_html)
        closed_html = self.client.get("/?status=closed").get_data(as_text=True)
        self.assertIn("昨日の試合", closed_html)
        with self.app.app_context():
            self.assertEqual(db.session.get(Post, past_id).status, "closed")

    def test_filter_sort_and_pagination(self):
        self.make_post(team_name="横浜球団", area="kanagawa-yokohama", event_date=date.today() + timedelta(days=2))
        self.make_post(team_name="千葉球団", area="chiba", event_date=date.today() + timedelta(days=4))
        self.make_post(team_name="早い球団", area="saitama", event_date=date.today() + timedelta(days=1))
        self.make_post(team_name="遅い球団", area="gunma", event_date=date.today() + timedelta(days=9))

        kanagawa = self.client.get("/?prefecture=kanagawa").get_data(as_text=True)
        self.assertIn("神奈川の募集中", kanagawa)
        self.assertIn("横浜球団", kanagawa)
        self.assertNotIn("千葉球団", kanagawa)
        yokohama = self.client.get("/?area=kanagawa-yokohama").get_data(as_text=True)
        self.assertIn("神奈川・横浜の募集中", yokohama)
        self.assertIn("横浜球団", yokohama)

        shonan = self.client.get("/?area=kanagawa-shonan").get_data(as_text=True)
        self.assertNotIn("横浜球団", shonan)

        ascending = self.client.get("/?sort=date_asc").get_data(as_text=True)
        self.assertLess(ascending.index("早い球団"), ascending.index("遅い球団"))
        descending = self.client.get("/?sort=date_desc").get_data(as_text=True)
        self.assertLess(descending.index("遅い球団"), descending.index("早い球団"))

        for index in range(PER_PAGE + 1):
            self.make_post(team_name=f"連番{index:02d}")
        page2 = self.client.get("/?page=2").get_data(as_text=True)
        self.assertIn("連番20", page2)
        self.assertNotIn("連番00", page2)

    def test_email_is_obfuscated(self):
        post_id = self.make_post(email="tester@example.com")
        html = self.client.get(f"/posts/{post_id}").get_data(as_text=True)
        self.assertNotIn("tester@example.com", html)
        self.assertNotIn("mailto:", html)
        user = base64.b64decode(re.search(r'data-u="([^"]+)"', html).group(1)).decode()[::-1]
        host = base64.b64decode(re.search(r'data-h="([^"]+)"', html).group(1)).decode()[::-1]
        self.assertEqual(f"{user}@{host}", "tester@example.com")

    def test_create_validation_and_csrf(self):
        page = self.client.get("/posts/new")
        token = self.csrf_from(page)
        missing = self.client.post("/posts/new", data={"csrf_token": token})
        self.assertIn("募集タイプを選択してください。", missing.get_data(as_text=True))

        mismatch = self.client.post(
            "/posts/new",
            data=self.payload(token, password_confirm="another-pass"),
        )
        self.assertIn("暗証番号（確認）が一致しません。", mismatch.get_data(as_text=True))

        past = self.client.post(
            "/posts/new",
            data=self.payload(token, event_date=(date.today() - timedelta(days=1)).isoformat()),
        )
        self.assertIn("試合日は今日以降を指定してください。", past.get_data(as_text=True))

        custom = self.client.post(
            "/posts/new",
            data=self.payload(token, time_slot="custom", time_start="18:00", time_end="09:00"),
        )
        self.assertIn("終了時刻は開始時刻より後にしてください。", custom.get_data(as_text=True))

        rejected = self.client.post("/posts/new", data={"post_type": "helper"})
        self.assertEqual(rejected.status_code, 400)
        self.assertIn("送信を確認できませんでした", rejected.get_data(as_text=True))

    def test_create_edit_close_and_delete(self):
        token = self.csrf_from(self.client.get("/posts/new"))
        created = self.client.post("/posts/new", data=self.payload(token), follow_redirects=False)
        self.assertEqual(created.status_code, 302)
        path = urlparse(created.headers["Location"]).path
        detail = self.client.get(path).get_data(as_text=True)
        self.assertIn("テスト球団", detail)
        self.assertNotIn("captain@example.com", detail)
        self.assertNotIn("mailto:", detail)

        manage = self.client.get(path + "/manage")
        manage_html = manage.get_data(as_text=True)
        self.assertIn("変更を保存", manage_html)
        updated = self.client.post(
            path + "/manage",
            data=self.payload(self.csrf_from(manage), action="update", team_name="更新球団", password="", password_confirm=""),
            follow_redirects=True,
        )
        self.assertIn("更新球団", updated.get_data(as_text=True))

        manage = self.client.get(path + "/manage")
        closed = self.client.post(
            path + "/manage",
            data={"csrf_token": self.csrf_from(manage), "action": "close"},
            follow_redirects=True,
        )
        self.assertIn("募集終了", closed.get_data(as_text=True))
        self.assertNotIn("更新球団", self.client.get("/").get_data(as_text=True))
        self.assertIn("更新球団", self.client.get("/?status=closed").get_data(as_text=True))

        manage = self.client.get(path + "/manage")
        reopened = self.client.post(
            path + "/manage",
            data={"csrf_token": self.csrf_from(manage), "action": "reopen"},
            follow_redirects=True,
        )
        self.assertIn("募集中に戻しました", reopened.get_data(as_text=True))

        manage = self.client.get(path + "/manage")
        deleted = self.client.post(
            path + "/manage",
            data={"csrf_token": self.csrf_from(manage), "action": "delete"},
            follow_redirects=True,
        )
        self.assertIn("投稿を削除しました", deleted.get_data(as_text=True))
        self.assertNotIn("更新球団", deleted.get_data(as_text=True))

    def test_password_gate_and_reopen_block(self):
        post_id = self.make_post()
        manage_url = f"/posts/{post_id}/manage"
        token = self.csrf_from(self.client.get(manage_url))
        wrong = self.client.post(manage_url, data={"csrf_token": token, "action": "unlock", "password": "wrong-pass"})
        self.assertIn("暗証番号が違います。", wrong.get_data(as_text=True))

        blocked = self.client.post(
            manage_url,
            data=self.payload(token, action="update"),
            follow_redirects=True,
        )
        self.assertIn("先に暗証番号を入力してください。", blocked.get_data(as_text=True))

        unlocked = self.client.post(
            manage_url,
            data={"csrf_token": token, "action": "unlock", "password": "secret12"},
            follow_redirects=True,
        )
        self.assertIn("変更を保存", unlocked.get_data(as_text=True))

        past_id = self.make_post(team_name="過ぎた試合", event_date=date.today() - timedelta(days=2))
        past_url = f"/posts/{past_id}/manage"
        past_token = self.csrf_from(self.client.get(past_url))
        self.client.post(past_url, data={"csrf_token": past_token, "action": "unlock", "password": "secret12"})
        refused = self.client.post(
            past_url,
            data={"csrf_token": past_token, "action": "reopen"},
            follow_redirects=True,
        )
        self.assertIn("募集中に戻せません", refused.get_data(as_text=True))
        with self.app.app_context():
            self.assertEqual(db.session.get(Post, past_id).status, "closed")

    def test_too_many_password_attempts(self):
        post_id = self.make_post()
        manage_url = f"/posts/{post_id}/manage"
        token = self.csrf_from(self.client.get(manage_url))
        last = None
        for _ in range(6):
            last = self.client.post(
                manage_url,
                data={"csrf_token": token, "action": "unlock", "password": "wrong-pass"},
            )
        self.assertIn("試行が多すぎます", last.get_data(as_text=True))

    def test_search_date_and_same_day_match(self):
        day = date.today() + timedelta(days=4)
        ground_id = self.make_post(
            team_name="会場あり球団",
            post_type="with_ground",
            event_date=day,
            place_detail="荒川砂町グラウンド",
            level="enjoy",
            headcount="12人",
            positions="捕手",
        )
        seeker_id = self.make_post(
            team_name="会場なし球団",
            post_type="without_ground",
            event_date=day,
            area="chiba",
        )
        self.make_post(team_name="別の日の球団", event_date=day + timedelta(days=3))

        found = self.client.get("/?q=砂町").get_data(as_text=True)
        self.assertIn("会場あり球団", found)
        self.assertNotIn("会場なし球団", found)
        self.assertNotIn("tester@example.com", found)

        missed = self.client.get("/?q=%").get_data(as_text=True)
        self.assertNotIn("会場あり球団", missed)

        only_day = self.client.get(f"/?on={day.isoformat()}").get_data(as_text=True)
        self.assertIn("会場あり球団", only_day)
        self.assertIn("会場なし球団", only_day)
        self.assertNotIn("別の日の球団", only_day)
        self.assertIn(f"{day.month}月{day.day}日", only_day)

        detail = self.client.get(f"/posts/{ground_id}").get_data(as_text=True)
        self.assertIn("この日、グラウンドを探しているチーム", detail)
        self.assertIn("会場なし球団", detail)
        self.assertIn("エンジョイ", detail)
        self.assertIn("地図で開く", detail)
        self.assertIn("maps/search", detail)
        self.assertIn("この募集を共有", detail)
        self.assertNotIn("tester@example.com", detail)

        seeker = self.client.get(f"/posts/{seeker_id}").get_data(as_text=True)
        self.assertIn("この日、グラウンドがあるチーム", seeker)
        self.assertIn("会場あり球団", seeker)

    def test_level_fields_and_no_phone(self):
        token = self.csrf_from(self.client.get("/posts/new"))
        form_html = self.client.get("/posts/new").get_data(as_text=True)
        self.assertNotIn("電話番号", form_html)
        self.assertNotIn('name="phone"', form_html)

        created = self.client.post(
            "/posts/new",
            data=self.payload(token, level="mid", positions="投手"),
            follow_redirects=True,
        )
        html = created.get_data(as_text=True)
        self.assertIn("中級", html)
        self.assertIn("投手", html)
        self.assertIn("メールで連絡する", html)
        self.assertNotIn("電話する", html)
        self.assertNotIn("tel:", html)
        self.assertNotIn('name="phone"', html)

    def test_list_shows_updated_label(self):
        self.make_post(team_name="更新表示球団")
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("更新表示球団", html)
        self.assertRegex(html, r"更新 (たった今|\d+分前|今日 \d{2}:\d{2})")

    def test_level_and_weekend_filters(self):
        import jpholiday

        saturday = self.next_weekday(5)
        weekday = saturday + timedelta(days=2)
        while jpholiday.is_holiday(weekday) or weekday.weekday() >= 5:
            weekday += timedelta(days=1)
        holiday = None
        for offset in range(1, 400):
            day = date.today() + timedelta(days=offset)
            if jpholiday.is_holiday(day) and day.weekday() < 5:
                holiday = day
                break
        self.assertIsNotNone(holiday)

        self.make_post(team_name="土曜エンジョイ", event_date=saturday, level="enjoy")
        self.make_post(team_name="平日しっかり", event_date=weekday, level="strong")
        self.make_post(team_name="土曜中級", event_date=saturday, level="mid")
        self.make_post(team_name="祝日募集", event_date=holiday, level="enjoy")

        weekend = self.client.get("/?weekend=1").get_data(as_text=True)
        self.assertIn("土日祝の募集中", weekend)
        self.assertIn("土日祝だけ", weekend)
        self.assertIn("土曜エンジョイ", weekend)
        self.assertIn("土曜中級", weekend)
        self.assertIn("祝日募集", weekend)
        self.assertNotIn("平日しっかり", weekend)

        mid = self.client.get("/?level=mid").get_data(as_text=True)
        self.assertIn("中級", mid)
        self.assertIn("土曜中級", mid)
        self.assertNotIn("土曜エンジョイ", mid)
        self.assertNotIn("月曜しっかり", mid)

    def test_similar_post_requires_confirmation(self):
        day = date.today() + timedelta(days=6)
        self.make_post(
            team_name="既存の会場あり",
            post_type="with_ground",
            event_date=day,
            area="tokyo-23",
        )
        token = self.csrf_from(self.client.get("/posts/new"))
        blocked = self.client.post(
            "/posts/new",
            data=self.payload(token, event_date=day.isoformat(), area="tokyo-23", post_type="with_ground"),
        )
        html = blocked.get_data(as_text=True)
        self.assertEqual(blocked.status_code, 200)
        self.assertIn("似た募集がすでにあります", html)
        self.assertIn("既存の会場あり", html)
        self.assertIn('name="confirm_similar"', html)
        with self.app.app_context():
            self.assertEqual(db.session.query(Post).count(), 1)

        created = self.client.post(
            "/posts/new",
            data=self.payload(
                token,
                event_date=day.isoformat(),
                area="tokyo-23",
                post_type="with_ground",
                team_name="あとから投稿",
                confirm_similar="1",
            ),
            follow_redirects=True,
        )
        self.assertIn("あとから投稿", created.get_data(as_text=True))
        with self.app.app_context():
            self.assertEqual(db.session.query(Post).count(), 2)

    def test_ics_and_report_and_guide(self):
        post_id = self.make_post(team_name="カレンダー球団", place_detail="葛飾グラウンド")
        guide = self.client.get("/guide").get_data(as_text=True)
        self.assertIn("利用ガイド", guide)
        self.assertIn("暗証番号", guide)

        ics = self.client.get(f"/posts/{post_id}.ics")
        self.assertEqual(ics.status_code, 200)
        self.assertIn("text/calendar", ics.headers.get("Content-Type", ""))
        body = ics.get_data(as_text=True)
        self.assertIn("BEGIN:VCALENDAR", body)
        self.assertIn("カレンダー球団", body)
        self.assertIn("葛飾グラウンド", body)

        detail = self.client.get(f"/posts/{post_id}").get_data(as_text=True)
        self.assertIn("カレンダーに追加", detail)
        self.assertIn("通報する", detail)

        report_page = self.client.get(f"/posts/{post_id}/report")
        token = self.csrf_from(report_page)
        missing = self.client.post(f"/posts/{post_id}/report", data={"csrf_token": token})
        self.assertIn("通報の理由を選んでください。", missing.get_data(as_text=True))

        sent = self.client.post(
            f"/posts/{post_id}/report",
            data={"csrf_token": token, "reason": "spam", "comment": "宣伝っぽい"},
            follow_redirects=True,
        )
        self.assertIn("通報を受け付けました", sent.get_data(as_text=True))
        with self.app.app_context():
            report = db.session.query(Report).filter_by(post_id=post_id).one()
            self.assertEqual(report.reason, "spam")
            self.assertEqual(report.comment, "宣伝っぽい")

    def test_counterpart_prefers_same_prefecture(self):
        day = date.today() + timedelta(days=5)
        ground_id = self.make_post(
            team_name="東京グラウンド",
            post_type="with_ground",
            area="tokyo-23",
            event_date=day,
        )
        self.make_post(
            team_name="千葉探し",
            post_type="without_ground",
            area="chiba",
            event_date=day,
        )
        self.make_post(
            team_name="多摩探し",
            post_type="without_ground",
            area="tokyo-tama",
            event_date=day,
        )
        detail = self.client.get(f"/posts/{ground_id}").get_data(as_text=True)
        self.assertIn("同じ都道府県の募集を先に表示しています。", detail)
        self.assertLess(detail.index("多摩探し"), detail.index("千葉探し"))


if __name__ == "__main__":
    unittest.main()
