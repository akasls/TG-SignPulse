import sys
import os
from pathlib import Path

# Add project root to sys.path to allow imports from backend
# Assumes script is run from project root or scripts/ directory
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.models.user import User
from backend.core.config import get_settings
from backend.core.security import hash_password

def reset_password(username="admin", new_password="admin123"):
    print(f"Project Root: {project_root}")
    
    try:
        settings = get_settings()
        db_url = settings.database_url
        print(f"Database URL: {db_url}")
        
        # Ensure we are using absolute path for sqlite if it's relative
        if db_url.startswith("sqlite:///"):
            db_path_str = db_url.replace("sqlite:///", "")
            # If it's a relative path, make it absolute relative to project root (or wherever config says)
            # But config.py logic should handle it.
            # However, if running from script, CWD matters for relative paths.
            # backend/core/config.py uses settings.data_dir which defaults to /data or C:\data or env var.
            pass

        engine = create_engine(db_url)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()
        
        user = db.query(User).filter(User.username == username).first()
        if not user:
            print(f"User '{username}' not found. Creating new user.")
            user = User(username=username, password_hash=hash_password(new_password))
            db.add(user)
        else:
            print(f"User '{username}' found. Resetting password.")
            user.password_hash = hash_password(new_password)
            user.totp_secret = None # Reset TOTP too just in case
            
        db.commit()
        print(f"SUCCESS: Password for '{username}' has been reset to '{new_password}'. TOTP disabled.")
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if 'db' in locals():
            db.close()

if __name__ == "__main__":
    if len(sys.argv) > 2:
        reset_password(sys.argv[1], sys.argv[2])
    elif len(sys.argv) > 1:
        reset_password(sys.argv[1])
    else:
        reset_password()
