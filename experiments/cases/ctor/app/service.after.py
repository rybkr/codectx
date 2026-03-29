from app.models import UserStore


def build_store(url: str) -> UserStore:
    return UserStore(url)
