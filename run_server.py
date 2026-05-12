#!/usr/bin/env python
import sys
import os

# 添加父目录到路径，这样相对导入可以工作
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 切换到父目录
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uvicorn
from app.main import app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)