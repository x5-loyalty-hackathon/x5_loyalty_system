"""Editable wallpaper catalog for the process-local demo, not measured balance."""
from dataclasses import dataclass


DEFAULT_WALLPAPER_ID = "wallpaper_default"


@dataclass(frozen=True)
class Wallpaper:
    item_id: str
    title: str
    description: str
    unlock_level: int


# Unlock XP is derived from these levels and the existing XP_PER_LEVEL rule.
# Individual wallpapers can be freely switched once the level is reached.
WALLPAPER_CATALOG = (
    Wallpaper(DEFAULT_WALLPAPER_ID, "Тёплый дом", "Базовое оформление кухни", 1),
    Wallpaper("wallpaper_mint", "Мятное утро", "Свежие мятные обои", 2),
    Wallpaper("wallpaper_sunset", "Персиковый закат", "Мягкие персиковые обои", 2),
    Wallpaper("wallpaper_sky", "Небесная кухня", "Светлые небесно-голубые обои", 2),
    Wallpaper("wallpaper_night", "Звёздный вечер", "Тёмные обои со звёздами", 3),
    Wallpaper("wallpaper_berry", "Ягодный уют", "Обои в тёплых ягодных оттенках", 4),
)
WALLPAPERS_BY_ID = {item.item_id: item for item in WALLPAPER_CATALOG}


@dataclass
class HomeDecorationRecord:
    goal_item_id: str | None = None
    applied_item_id: str = DEFAULT_WALLPAPER_ID


class HomeDecorationItemNotFound(ValueError):
    pass


class HomeDecorationItemLocked(ValueError):
    pass
