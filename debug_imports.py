import sys
import os

print("Current working directory:", os.getcwd())
print("Python path:", sys.path)

try:
    print("Attempting to import app...")
    import app
    print("Successfully imported app.")
except Exception as e:
    print(f"Failed to import app: {e}")

try:
    print("Attempting to import extensions...")
    import extensions
    print("Successfully imported extensions.")
except Exception as e:
    print(f"Failed to import extensions: {e}")

try:
    print("Attempting to import models...")
    from app.models import models
    print("Successfully imported models.")
except Exception as e:
    print(f"Failed to import models: {e}")

try:
    print("Attempting to create app...")
    from app import create_app
    app = create_app()
    print("Successfully created app.")
except Exception as e:
    print(f"Failed to create app: {e}")
