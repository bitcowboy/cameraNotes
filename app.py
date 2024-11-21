from flask import Flask, render_template, request, jsonify
import os
import uuid
import base64
from openai import OpenAI

system_prompt = """
你看到什么？
如果是食物，请告诉我食物的名称和热量。
如果是房号，告诉我房间号码。
如果是小票，请告诉我小票上的信息。
如果是其它信息，请告诉我你认为的信息。
"""

client = OpenAI()

app = Flask(__name__)

# Function to encode the image
def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def analyze_image(image_path):
    base64_image = encode_image(image_path)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": [{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}", "detail": "low"}}]}
        ]
    )   
    print(response.choices[0].message.content)
    return response.choices[0].message.content

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    if 'image' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    # Generate a unique filename with the correct extension
    unique_filename = f"{uuid.uuid4()}.jpg"
    file_path = os.path.join('uploads', unique_filename)
    file.save(file_path)

    analysis = analyze_image(file_path)
    return jsonify({'success': True, 'file_path': file_path, 'result': analysis})

if __name__ == '__main__':
    if not os.path.exists('uploads'):
        os.makedirs('uploads')
    app.run(host='0.0.0.0', debug=True, ssl_context='adhoc')
