"""
Django settings for backend project.
"""

from pathlib import Path
import os
from dotenv import load_dotenv
import dj_database_url

# ------------------------------------
# Paths / .env
# ------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# ------------------------------------
# Seguridad / Debug
# ------------------------------------
SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-not-secret")
DEBUG = os.getenv("DEBUG", "False").lower() == "true"

def _csv_env(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name, "")
    if not raw:
        return default
    return [x.strip() for x in raw.split(",") if x.strip()]

if DEBUG:
    # Desarrollo: abierto y cómodo
    CORS_ALLOW_ALL_ORIGINS = True
    CORS_ALLOW_CREDENTIALS = True
    ALLOWED_HOSTS = ["*"]
    SESSION_COOKIE_SAMESITE = "Lax"
    CSRF_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
else:
    # Producción: más estricto
    CORS_ALLOW_ALL_ORIGINS = os.getenv("CORS_ALLOW_ALL_ORIGINS", "False").lower() == "true"
    CORS_ALLOWED_ORIGINS = _csv_env(
        "CORS_ALLOWED_ORIGINS",
        ["https://si-2-test1-app.vercel.app"]
    )
    CORS_ALLOW_CREDENTIALS = True
    ALLOWED_HOSTS = _csv_env("ALLOWED_HOSTS", ["127.0.0.1", "localhost", "si2-test1-appbackend.onrender.com"])
    SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "None")
    CSRF_COOKIE_SAMESITE = os.getenv("CSRF_COOKIE_SAMESITE", "None")
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "True").lower() == "true"
    CSRF_COOKIE_SECURE = os.getenv("CSRF_COOKIE_SECURE", "True").lower() == "true"

    # Configuraciones adicionales de seguridad para producción
    SESSION_COOKIE_HTTPONLY = os.getenv("SESSION_COOKIE_HTTPONLY", "True").lower() == "true"
    CSRF_COOKIE_HTTPONLY = os.getenv("CSRF_COOKIE_HTTPONLY", "True").lower() == "true"

    # Configuraciones SSL adicionales
    SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = os.getenv("SECURE_HSTS_INCLUDE_SUBDOMAINS", "True").lower() == "true"
    SECURE_HSTS_PRELOAD = os.getenv("SECURE_HSTS_PRELOAD", "True").lower() == "true"
    SECURE_CONTENT_TYPE_NOSNIFF = os.getenv("SECURE_CONTENT_TYPE_NOSNIFF", "True").lower() == "true"
    SECURE_BROWSER_XSS_FILTER = os.getenv("SECURE_BROWSER_XSS_FILTER", "True").lower() == "true"
    X_FRAME_OPTIONS = os.getenv("X_FRAME_OPTIONS", "DENY")

# Configuraciones adicionales de CORS
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
]

CORS_ALLOW_METHODS = [
    'DELETE',
    'GET',
    'OPTIONS',
    'PATCH',
    'POST',
    'PUT',
]

CSRF_TRUSTED_ORIGINS = _csv_env(
    "CSRF_TRUSTED_ORIGINS",
    [
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "https://si-2-test1-app.vercel.app",
        "https://si2-test1-appbackend.onrender.com",
    ]
)

CSRF_COOKIE_NAME = "csrftoken"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 0 if DEBUG else 60 * 60 * 24 * 30  # 30 días
SECURE_SSL_REDIRECT = not DEBUG

# ------------------------------------
# Apps
# ------------------------------------
INSTALLED_APPS = [
    "corsheaders",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "django_filters",
    'django_extensions',

    "api",  # tu app
]

# ------------------------------------
# Middleware
# ------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "backend.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "backend.wsgi.application"

# ------------------------------------
# DATABASES - Configuración para conexión directa a Supabase usando .env
# ------------------------------------

def get_database_config():
    """
    Configura la base de datos usando Session pooler de Supabase con variables del .env
    """
    # Variables para Session pooler desde .env
    db_host = os.getenv("DB_HOST", "aws-1-sa-east-1.pooler.supabase.com")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "postgres")
    db_password = os.getenv("DB_PASSWORD")
    db_user = os.getenv("DB_USER", "postgres.fbqwiducdgnfdzpgiczq")

    if not db_password:
        raise ValueError("DB_PASSWORD es requerida en las variables de entorno")

    # Configuración usando Session pooler (puerto 5432)
    config = {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': db_name,
        'USER': db_user,
        'PASSWORD': db_password,
        'HOST': db_host,
        'PORT': int(db_port),
        'OPTIONS': {"sslmode": "require"},
        'CONN_MAX_AGE': 300,  # Para Session pooler, conexiones de duración media
        'CONN_HEALTH_CHECKS': True,  # Verificar conexiones antes de usar
    }

    # Logging para debug (sin exponer credenciales)
    if not DEBUG:
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Using Session pooler - Host: {db_host}:{db_port}, User: {db_user[:20]}...")

    return config

DATABASES = {
    "default": get_database_config()
}

# Logging adicional para debug de conexión en producción
if not DEBUG:
    import logging
    logger = logging.getLogger(__name__)
    db_config = DATABASES["default"]
    logger.info(f"Database config - Host: {db_config.get('HOST', 'N/A')}, Port: {db_config.get('PORT', 'N/A')}")

# ------------------------------------
# Password validators
# ------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ------------------------------------
# Localización
# ------------------------------------
LANGUAGE_CODE = "es"
TIME_ZONE = "America/La_Paz"
USE_I18N = True
USE_TZ = True

# ------------------------------------
# Archivos estáticos (WhiteNoise)
# ------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# ------------------------------------
# DRF
# ------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",

    ],

}

# ------------------------------------
# Otros
# ------------------------------------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ------------------------------------
# Frontend / Email (opcional)
# ------------------------------------
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "no-reply@smart-condominium.local")

EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True") == "True"
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "False") == "True"

# ------------------------------------
# Logging sencillo
# ------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "{levelname} {asctime} {module} {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "api": {"handlers": ["console"], "level": "DEBUG", "propagate": False},
    },
}

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "ai-detection-images")
SUPABASE_STORAGE_URL = f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_STORAGE_BUCKET}"

# ------------------------------------
# Configuración de IA
# ------------------------------------
AI_IMAGE_SETTINGS = {
    'MAX_SIZE': (1920, 1080),
    'THUMBNAIL_SIZE': (800, 600),
    'JPEG_QUALITY': int(os.getenv("AI_JPEG_QUALITY", "85")),
    'MAX_FILE_SIZE_MB': 5,
    'FACE_TOLERANCE': float(os.getenv("AI_FACE_TOLERANCE", "0.6")),
    'PLATE_CONFIDENCE_THRESHOLD': float(os.getenv("AI_PLATE_CONFIDENCE_THRESHOLD", "0.5")),
}

# ------------------------------------
# Configuración del microservicio de IA
# ------------------------------------
AI_MICROSERVICE_URL = os.getenv('AI_MICROSERVICE_URL', 'http://localhost:8001')
