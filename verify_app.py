import sys
import os

# Add current dir to path just in case
sys.path.append(os.getcwd())

try:
    import app
    print("SUCCESS: app imported successfully")
    
    # Initialize DB (create tables if not exist)
    print("Initializing Database...")
    try:
        app.init_db()
        print("DB Initialized.")
    except Exception as e:
         print(f"DB Init Failed: {e}")

    print("Testing route '/api/processes'...")
    with app.app.test_client() as client:
        try:
            response = client.get('/api/processes')
            print(f"Status Code: {response.status_code}")
            if response.status_code != 200:
                print("Error Response Body:")
                print(response.data.decode('utf-8'))
        except Exception as req_err:
             print(f"Request Exception: {req_err}")
             import traceback
             traceback.print_exc()

except SyntaxError as e:
    print(f"SYNTAX ERROR: {e}")
    print(f"File: {e.filename}, Line: {e.lineno}, Offset: {e.offset}")
    print(f"Text: {e.text}")
except Exception as e:
    print(f"RUNTIME ERROR: {e}")
    import traceback
    traceback.print_exc()
