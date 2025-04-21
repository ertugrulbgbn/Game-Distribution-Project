import os

# Temel dizin yolunu belirle
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Güvenlik ayarları
SECRET_KEY = 'your-secret-key-here'  # Güvenlik için rastgele bir anahtar oluşturun
DEBUG = True  # Geliştirme ortamında True, canlı ortamda False olmalı
ALLOWED_HOSTS = []  # Canlı ortamda domain adınızı ekleyin

# Uygulama tanımları
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Kendi uygulamalarınız
    'games',
    'users',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'backend.urls'

# Şablon ayarları
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
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

WSGI_APPLICATION = 'backend.wsgi.application'

# Veritabanı ayarları
DATABASES = {
    'default': {
        'ENGINE': 'djongo',
        'NAME': 'game_distribution_db',
        'CLIENT': {
            'host': 'mongodb+srv://cluster0.msdsuq7.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0',
            'port': 27017,
            'username': 'MongoDB',
            'password': '12345.',
            'authSource': 'admin',
        }
    }
}

# Şifre doğrulama ayarları
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Uluslararasılaştırma ayarları
LANGUAGE_CODE = 'tr-tr'
TIME_ZONE = 'Europe/Istanbul'
USE_I18N = True
USE_L10N = True
USE_TZ = True

# Statik dosya ayarları
STATIC_URL = '/static/'
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static'),
]

# Medya dosyaları (yüklenen dosyalar) için ayarlar
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Django 3.2+ için DEFAULT_AUTO_FIELD tanımlaması
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'