from google import genai

client = genai.Client()

resp = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="Say only the word: OK"
)

print(resp.text)
