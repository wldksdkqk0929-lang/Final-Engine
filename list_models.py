import os
import google.generativeai as genai

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print("❌ API Key not found!")
else:
    genai.configure(api_key=api_key)
    print("📋 Available Models for your Key:")
    try:
        for m in genai.list_models():
            # 텍스트 생성이 가능한 모델만 출력
            if 'generateContent' in m.supported_generation_methods:
                print(f" - {m.name}")
    except Exception as e:
        print(f"❌ Error listing models: {e}")
