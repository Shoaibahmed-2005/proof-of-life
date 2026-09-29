from pathlib import Path
from typing import Any, List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ — used to resolve default data paths regardless of the working directory
BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore"
    )

    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Jeevan Suraksha Backend"

    # CORS Origins (accepts JSON list or comma-separated string)
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
    ]
    # Also allow the portal when opened from another device on the local network.
    CORS_ALLOW_LAN: bool = True
    # At startup, check that the backend answers on its own LAN address.
    LAN_SELF_CHECK: bool = True

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Any) -> Any:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        import json
        if isinstance(v, str) and v.startswith("["):
            return json.loads(v)
        return v

    # ── Security ────────────────────────────────────────────────────────
    SECRET_KEY: str = "secret-key-change-me-in-production"
    OFFICER_TOKEN_TTL_SECONDS: int = 8 * 3600
    # Seeded on first start if the officers table is empty (demo only)
    DEMO_OFFICER_USERNAME: str = "officer"
    DEMO_OFFICER_PASSWORD: str = "officer123"
    DEMO_OFFICER_NAME: str = "Demo Verification Officer"
    # Fernet key for encrypting face templates at rest. If empty, a key is
    # generated once and stored in DATA_DIR/template.key (development only).
    TEMPLATE_KEY: str = ""
    # PEM private key (P-256) that signs life-certificate credentials. If
    # empty, one is generated once in DATA_DIR/issuer_key.pem (development).
    ISSUER_KEY_PEM: str = ""

    # ── Storage ─────────────────────────────────────────────────────────
    DATA_DIR: Path = BACKEND_DIR / "data"
    DATABASE_URL: str = ""  # default: sqlite:///<DATA_DIR>/iob.db

    # ── Sessions / QR ───────────────────────────────────────────────────
    SESSION_EXPIRY_SECONDS: int = 300  # 5 minutes
    # Base URL the phone uses to reach this backend (put into the QR code).
    # Empty = auto: this machine's LAN IP and the port the request arrived on.
    PUBLIC_BASE_URL: str = ""
    # Max allowed difference between the phone's signed timestamp and server time
    TIMESTAMP_MAX_SKEW_SECONDS: int = 120
    CHALLENGE_TIMEOUT_SECONDS: int = 8

    # ── Liveness ────────────────────────────────────────────────────────
    BPM_MIN: float = 40
    BPM_MAX: float = 220
    # Minimum rPPG SNR in dB for LIFE_CERTIFICATE / ENROLLMENT payloads.
    # PLACEHOLDER — calibrate from phone logs (TESTING_CHECKLIST.md, M2 tests 2.5/2.8).
    MIN_SNR_DB: float = 3.0
    # The app's stability gate (sent in the QR code, so tuning needs no app rebuild).
    # Change these only from measured data (scan diagnostics; see
    # scripts/calibrate_thresholds.py scans).
    RPPG_WINDOW_SEC: float = 10.0
    RPPG_STABLE_COUNT: int = 5
    RPPG_STABLE_TOLERANCE_BPM: float = 3.0
    RPPG_SCAN_TIMEOUT_SEC: float = 30.0
    # Legacy AUTH flow (pre-milestone app): linear peak ratio, kept unchanged.
    LEGACY_MIN_SNR: float = 3.5

    # ── Face match (three-band decision) ────────────────────────────────
    # PLACEHOLDERS — must be calibrated on our own scans with
    # scripts/calibrate_thresholds.py before the demo. Do not copy values
    # from papers or the internet: they depend on our model and cameras.
    FACE_T_HIGH: float = 0.70
    FACE_T_LOW: float = 0.50
    # Minimum similarity to the never-changing anchor template for an auto-approval
    # and for any template update (prevents slow drift to another person).
    FACE_ANCHOR_MIN: float = 0.55
    # Weight of the new scan when blending into current_template.
    TEMPLATE_BLEND_ALPHA: float = 0.10
    FACE_MODEL_VERSION: str = "mobilefacenet-192-v1"  # must match FaceEmbedder.MODEL_VERSION in the app

    # ── Pension status rules ────────────────────────────────────────────
    MAX_FAILED_ATTEMPTS: int = 3
    # Life certificates are due by this date (MM-DD) each year; pensioners
    # without an issued certificate for the year are frozen after it.
    CERTIFICATE_DEADLINE: str = "11-30"

    # Log every face-match score to DATA_DIR/match_scores.csv for calibration
    SCORE_LOG_ENABLED: bool = True

    @property
    def database_url(self) -> str:
        return self.DATABASE_URL or f"sqlite:///{(self.DATA_DIR / 'iob.db').as_posix()}"


settings = Settings()
