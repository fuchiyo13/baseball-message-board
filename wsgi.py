"""開発サーバーの起動: python wsgi.py

環境変数:
  SECRET_KEY    セッションの署名キー。未設定なら instance/secret_key を使う
  DATABASE_URL  未設定なら SQLite（instance/board.db）
                PostgreSQL の例: postgresql://user:pass@localhost:5432/baseball
  PORT          待ち受けポート。既定は 5000
  FLASK_DEBUG   1 のときデバッガを有効にする
"""

import os

from board import create_app

app = create_app()

if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=int(os.environ.get("PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG") == "1",
    )
