import os
import sys
from pathlib import Path

# Add project to path
sys.path.append(str(Path(__file__).parent))

# Load settings manually to check
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

try:
    import django
    django.setup()
    
    from django.conf import settings
    from django.db import connection
    
    print("✅ Django setup successful!")
    print(f"📁 Project: {settings.BASE_DIR}")
    print(f"🔑 Secret Key: {'Set' if settings.SECRET_KEY else 'Not Set'}")
    print(f"🐛 Debug: {settings.DEBUG}")
    
    # Test database connection
    with connection.cursor() as cursor:
        cursor.execute("SELECT version();")
        db_version = cursor.fetchone()
        print(f"✅ Database connected: PostgreSQL {db_version[0]}")
        
    print(f"📊 Database Name: {connection.settings_dict['NAME']}")
    print(f"🌍 Database Host: {connection.settings_dict['HOST']}")
    print(f"🔌 Database Port: {connection.settings_dict['PORT']}")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()