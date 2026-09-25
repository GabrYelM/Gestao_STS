import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATABASE_PATH = os.environ.get(
    "STSPE_DB_PATH", os.path.join(BASE_DIR, "stspe.db")
)

UPLOAD_FOLDER = os.environ.get(
    "STSPE_UPLOAD_FOLDER", os.path.join(BASE_DIR, "uploads_tmp")
)

BACKUP_FOLDER = os.environ.get(
    "STSPE_BACKUP_FOLDER", os.path.join(BASE_DIR, "backups")
)

ALLOWED_EXTENSIONS_AT02 = {"csv"}
ALLOWED_EXTENSIONS_WEBSSAS = {"xml"}

MAX_FORM_PARTS = 100000
MAX_FORM_MEMORY_SIZE = 50 * 1024 * 1024
