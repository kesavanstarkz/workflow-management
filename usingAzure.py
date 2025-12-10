from openai import OpenAI
import base64

# ---------------------------
# AZURE OPENAI CONFIG
# ---------------------------
endpoint = "https://ai-foundary-rag.openai.azure.com/openai/v1"
deployment_name = "gpt-4o"
api_key = "DhoAt9lA57PwGhQykkSEL62W7KoXEpO48AnhFYQK3aYyhXtmJlxKJQQJ99BLAC77bzfXJ3w3AAAAACOG5pmr"

client = OpenAI(
    base_url=endpoint,
    api_key=api_key
)

# ---------------------------
# Encode image to base64
# ---------------------------
def encode_image(image_path):
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

IMAGE_PATH = "assets\Media (1).jpeg"
image_base64 = encode_image(IMAGE_PATH)

# ---------------------------
# GPT-4o Vision Request
# ---------------------------
response = client.chat.completions.create(
    model=deployment_name,
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "Extract only the streak number from this image and return response strictly in this format: <number> days completed(example: 43 days completed). Return nothing else."
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image_base64}"
                    }
                }
            ]
        }
    ],
)

# ---------------------------
# Output ONLY the result
# ---------------------------
result = response.choices[0].message.content.strip()
print(result)
