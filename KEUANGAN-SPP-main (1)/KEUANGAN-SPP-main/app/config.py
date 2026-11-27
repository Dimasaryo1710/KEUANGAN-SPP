# app/config.py
import os
from dotenv import load_dotenv
load_dotenv()
from datetime import timedelta

class Config:
    """Konfigurasi Aplikasi SPP Management"""
    
    MAIL_BACKEND = os.getenv('MAIL_BACKEND', 'file')
    MAIL_DEFAULT_SENDER = os.getenv('MAIL_DEFAULT_SENDER', 'spp@example.test')
    SCHEDULER_ENABLED = os.getenv('SCHEDULER_ENABLED', 'true').lower() == 'true'
    # Database
    SQLALCHEMY_DATABASE_URI = 'sqlite:///spp_management.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Security
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # Payment Gateway
    PAYMENT_GATEWAY_SECRET = os.environ.get('PAYMENT_GATEWAY_SECRET') or 'webhook-secret'
    
    # Email Configuration
    MAIL_SERVER = os.environ.get('MAIL_SERVER') or 'smtp.gmail.com'
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USE_TLS = os.getenv('MAIL_USE_TLS', 'true').lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    
    # Billing Configuration
    BILLING_DAYS_BEFORE_DUE = 14  # Due date 2 minggu setelah semester start
    OVERDUE_PENALTY_PER_DAY = 10000  # Rp 10.000 per hari
    OVERDUE_MAX_PENALTY = 500000  # Max penalty Rp 500.000
    
    # Scheduler Configuration
    SCHEDULER_API_ENABLED = True
    SCHEDULER_TIMEZONE = 'Asia/Jakarta'
    
    # AI Configuration
    AI_MODEL = 'gpt-3.5-turbo'  # Bisa diganti dengan model lain
    
    # Program Studi dan SPP Amount
    PROGRAM_STUDI_SPP = {
        'Teknik Informatika': 5000000,      # Rp 5 juta
        'Ekonomi': 4000000,                 # Rp 4 juta
        'Hukum': 3500000,                   # Rp 3.5 juta
        'Teknik Sipil': 5000000,            # Rp 5 juta
    }
    
class DevelopmentConfig(Config):
    """Development Configuration"""
    DEBUG = True
    TESTING = False

class TestingConfig(Config):
    """Testing Configuration"""
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    TESTING = True
    WTF_CSRF_ENABLED = False

class ProductionConfig(Config):
    """Production Configuration"""
    DEBUG = False
    TESTING = False

config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
