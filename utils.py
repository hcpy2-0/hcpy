import unicodedata
from datetime import datetime


def clean_international_text(text):
    # Normalize Unicode characters
    normalized = unicodedata.normalize("NFKD", text)
    # Remove non-ASCII characters
    ascii_text = normalized.encode("ASCII", "ignore").decode("ASCII")
    return ascii_text

def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
