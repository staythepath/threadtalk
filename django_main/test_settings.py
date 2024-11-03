# In test_settings.py
from .settings import *

DEBUG = True
ALLOWED_HOSTS = ['*']  # Or ['127.0.0.1', 'localhost'] for local testing

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_activitypub',

]

# TEST_RUNNER = 'django_nose.NoseTestSuiteRunner'
# NOSE_ARGS = [
#     '--nologcapture',  # Ensure logs are printed to console
#     '--nocapture',     # Avoid capturing stdout
# ]


LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{'
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        # Change 'django' to your specific module if needed
        'django': {
            'handlers': ['console'],
            'level': 'ERROR',  # Change to 'DEBUG' or 'INFO' if you want more detail
            'propagate': True,
        },
        # Add other loggers here if you need specific logs
        'your_module_name': {
            'handlers': ['console'],
            'level': 'DEBUG',  # Set to your desired level
            'propagate': False,
        },
    },
}


