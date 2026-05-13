from fastapi.testclient import TestClient
import sys
sys.path.insert(0, '/Users/hushizhe/Desktop/vibe-coding/ytb')

# 设置 PYTHONPATH
import os
os.chdir('/Users/hushizhe/Desktop/vibe-coding/ytb')
os.environ['PYTHONPATH'] = '/Users/hushizhe/Desktop/vibe-coding/ytb'

# 创建客户端
import uvicorn
from app.main import app

client = TestClient(app)

try:
    resp = client.post('/check', headers={'Authorization': '983982f6-d646-4ad0-a50c-d33fd752fbe5'})
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text}")
except Exception as e:
    import traceback
    print(f"Error: {e}")
    traceback.print_exc()