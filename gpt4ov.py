import base64
from openai import OpenAI

system_prompt = "你看到什么？如果是食物，请告诉我食物的名称和热量。如果是房号，告诉我房间号码。如果是小票，请告诉我小票上的信息。"

client = OpenAI()

# Function to encode the image
def encode_image(image_path):
  with open(image_path, "rb") as image_file:
    return base64.b64encode(image_file.read()).decode('utf-8')

# Path to your image
image_path = "image.jpg"

# Getting the base64 string
base64_image = encode_image(image_path)

response = client.chat.completions.create(
  model="gpt-4o-mini",
  messages=[
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": system_prompt,
        },
        {
          "type": "image_url",
          "image_url": {
            "url":  f"data:image/jpeg;base64,{base64_image}",
            "detail": "low"
          },
        },
      ],
    }
  ],
)

# Print the response
print(response.choices[0])
print(response.usage)
