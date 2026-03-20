from dataclasses import dataclass
from pathlib import Path
import os
from typing import Optional


@dataclass(frozen=True)
class Settings:
    app_name: str
    athlete_name: str
    athlete_timezone: str
    database_path: Path
    intervals_base_url: str
    intervals_athlete_id: Optional[str]
    intervals_api_key: Optional[str]
    intervals_request_pause_seconds: float


def get_settings() -> Settings:
    root_dir = Path(__file__).resolve().parent.parent
    data_dir = root_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    database_path = Path(
        os.getenv("FITNESSAI_DATABASE_PATH", str(data_dir / "fitnessai.sqlite3"))
    )

    return Settings(
        app_name="fitnessai",
        athlete_name=os.getenv("FITNESSAI_ATHLETE_NAME", "Anatoly"),
        athlete_timezone=os.getenv("FITNESSAI_ATHLETE_TIMEZONE", "Europe/Madrid"),
        database_path=database_path,
        intervals_base_url=os.getenv(
            "INTERVALS_BASE_URL", "https://intervals.icu"
        ),
        intervals_athlete_id=os.getenv("INTERVALS_ATHLETE_ID"),
        intervals_api_key=os.getenv("INTERVALS_API_KEY"),
        intervals_request_pause_seconds=float(
            os.getenv("INTERVALS_REQUEST_PAUSE_SECONDS", "1.0")
        ),
    )
