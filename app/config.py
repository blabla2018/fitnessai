from dataclasses import dataclass
from pathlib import Path
import os
import re
from typing import Optional


@dataclass(frozen=True)
class Settings:
    app_name: str
    database_path: Path
    intervals_base_url: str
    intervals_athlete_id: Optional[str]
    intervals_api_key: Optional[str]


def _validate_intervals_athlete_id(athlete_id: Optional[str]) -> Optional[str]:
    if athlete_id is None or athlete_id == "":
        return athlete_id
    if not re.fullmatch(r"i?\d+", athlete_id):
        raise ValueError(
            "INTERVALS_ATHLETE_ID must be all digits or start with 'i' followed by digits."
        )
    return athlete_id


def get_settings() -> Settings:
    root_dir = Path(__file__).resolve().parent.parent
    data_dir = root_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    database_path = Path(
        os.getenv("FITNESSAI_DATABASE_PATH", str(data_dir / "fitnessai.sqlite3"))
    )

    return Settings(
        app_name="fitnessai",
        database_path=database_path,
        intervals_base_url=os.getenv("INTERVALS_BASE_URL", "https://intervals.icu").rstrip("/"),
        intervals_athlete_id=_validate_intervals_athlete_id(
            os.getenv("INTERVALS_ATHLETE_ID")
        ),
        intervals_api_key=os.getenv("INTERVALS_API_KEY"),
    )
