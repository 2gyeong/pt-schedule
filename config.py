import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
(BASE_DIR / "instance").mkdir(exist_ok=True)


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")
    ADMIN_NAME = os.environ.get("ADMIN_NAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin1234")
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + str(BASE_DIR / "instance" / "app.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
