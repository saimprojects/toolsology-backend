from __future__ import annotations

import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured

import cloudinary
import cloudinary.uploader
import cloudinary.api
import dj_database_url
from dotenv import load_dotenv

# Load .env file - explicitly from project root
BASE_DIR = Path(__file__).resolve().parent.parent
env_path = BASE_DIR / '.env'

if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    # Try to load from current directory as fallback
    load_dotenv()

# SECURITY
SECRET_KEY: str = os.environ.get('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    raise ImproperlyConfigured('DJANGO_SECRET_KEY is not set in environment variables')

DEBUG: bool = os.environ.get('DJANGO_DEBUG', 'False') == 'True'

# ALLOWED_HOSTS
ALLOWED_HOSTS: list[str] = ['localhost', '127.0.0.1']

# Environment se extra hosts add kar sakte ho
env_hosts = os.environ.get('DJANGO_ALLOWED_HOSTS', '')
if env_hosts:
    ALLOWED_HOSTS.extend([h.strip() for h in env_hosts.split(',') if h.strip()])

# Production mein Railway domain automatically add ho jayega agar environment variable ho
if os.environ.get('RAILWAY_PUBLIC_DOMAIN'):
    ALLOWED_HOSTS.append(os.environ.get('RAILWAY_PUBLIC_DOMAIN'))

# Development ke liye wildcard bhi allow (sirf local testing ke liye)
if DEBUG:
    ALLOWED_HOSTS.append('*')

# DATABASE CONFIGURATION - Smart local + production support
DATABASE_URL = os.environ.get('DATABASE_URL')

if DATABASE_URL:
    # Production / Railway mode
    try:
        db_config = dj_database_url.parse(DATABASE_URL, conn_max_age=600, ssl_require=True)
        
        # Verify it's PostgreSQL
        engine = db_config.get('ENGINE', '')
        if 'postgresql' not in engine and 'postgres' not in engine:
            raise ImproperlyConfigured(f'Database ENGINE should be PostgreSQL, got: {engine}')
            
        DATABASES = {'default': db_config}
        
    except Exception as e:
        raise ImproperlyConfigured(f'Failed to parse DATABASE_URL: {str(e)}')
else:
    # Local development fallback - Tumhara RT database
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': 'RT',
            'USER': 'postgres',
            'PASSWORD': 'saim',
            'HOST': 'localhost',
            'PORT': '5432',
        }
    }

# APPLICATIONS
INSTALLED_APPS = [
    'jazzmin',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'corsheaders',
    'rest_framework',
    'rest_framework.authtoken',
    'rest_framework_simplejwt',
    'ckeditor',
    'ckeditor_uploader',
    'cloudinary',
    'cloudinary_storage',

    'product',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# PASSWORD VALIDATORS
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# INTERNATIONALIZATION
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Karachi'
USE_I18N = True
USE_L10N = True
USE_TZ = True

# STATIC FILES
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# MEDIA / CLOUDINARY
MEDIA_URL = '/media/'
DEFAULT_FILE_STORAGE = 'cloudinary_storage.storage.MediaCloudinaryStorage'

# Cloudinary Configuration
CLOUD_NAME = os.environ.get('CLOUD_NAME')
API_KEY = os.environ.get('API_KEY')
API_SECRET = os.environ.get('API_SECRET')

if all([CLOUD_NAME, API_KEY, API_SECRET]):
    cloudinary.config(
        cloud_name=CLOUD_NAME,
        api_key=API_KEY,
        api_secret=API_SECRET,
    )
# Agar credentials nahi hain toh local mein bhi chalta rahega (silent fail)

# REST FRAMEWORK
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': ['rest_framework_simplejwt.authentication.JWTAuthentication'],
    'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.IsAuthenticatedOrReadOnly'],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 10,
}

# JWT
from datetime import timedelta
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# JAZZMIN
JAZZMIN_SETTINGS = {
    'site_title': 'Administration',
    'site_header': 'Administration',
    'site_brand': 'Admin',
    'welcome_sign': 'Welcome to Admin Panel',
    'show_sidebar': True,
    'navigation_expanded': False,
}

# CKEditor
CKEDITOR_UPLOAD_PATH = "ckeditor_uploads/"

CKEDITOR_CONFIGS = {
    "default": {
        "toolbar": [
            ["Bold", "Italic", "Underline"],
            ["NumberedList", "BulletedList"],
            ["Link", "Unlink"],
            ["RemoveFormat"],
        ],
        "height": 200,
        "width": "auto",
    }
}

# CORS - Local development ke liye common ports
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
]

# Agar environment mein extra origins hain toh add kar do
extra_origins = os.environ.get('CORS_ALLOWED_ORIGINS', '')
if extra_origins:
    CORS_ALLOWED_ORIGINS.extend([origin.strip() for origin in extra_origins.split(',') if origin.strip()])

CORS_ALLOW_CREDENTIALS = True

# CSRF TRUSTED ORIGINS
CSRF_TRUSTED_ORIGINS = [
    'http://localhost:5173',
    'http://localhost:3000',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    'http://127.0.0.1:5173',
]

# Railway production domain
if os.environ.get('RAILWAY_PUBLIC_DOMAIN'):
    CSRF_TRUSTED_ORIGINS.append(f"https://{os.environ.get('RAILWAY_PUBLIC_DOMAIN')}")
CSRF_TRUSTED_ORIGINS.append('https://*.railway.app')

# SECURE SETTINGS - Local mein off, production mein on
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG