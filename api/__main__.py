import os
import uvicorn

def main():
    uvicorn.run('api.main:app', host=os.getenv('OE_API_HOST','127.0.0.1'), port=int(os.getenv('OE_API_PORT','8000')), reload=True)
