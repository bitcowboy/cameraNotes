from flask import Flask, render_template, request, jsonify
import os
import uuid
import base64
from openai import OpenAI
import sqlite3
from datetime import datetime

system_prompt = """
你是一个智能助手。你会分析用户拍的照片，并给出分析其中的主题。根据不同的主题，调用相应的工具，帮助用户备忘、记录信息或解决问题。
如果是食物，请告诉我食物的名称和热量，并调用相应的函数做记录。
如果是房号，告诉我房间号码。
如果是小票，请告诉我小票上的信息。
如果是其它信息，请告诉我你认为的信息。

当你检测到主题时直接调用工具，不需要用户确认。
使用简体中文回答。
"""

tools = [
    {
        "type": "function",
        "function": {
            "name": "record_calories",
            "description": "记录用户吃的食物中包含的热量。当用户拍摄一张食物照片的时候请估计它们的热量并调用这个函数做记录。",
            "parameters": {
                "type": "object",
                "properties": {
                    "food_name": {
                        "type": "string",
                        "description": "食物的名称",
                    },
                    "calories": {
                        "type": "integer",
                        "description": "食物的热量",
                    },
                },
                "required": ["food_name", "calories"],
                "additionalProperties": False,
            },
        }
    }
]

client = OpenAI()

app = Flask(__name__)

# Initialize the SQLite database
def init_db():
    conn = sqlite3.connect('calories.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS calories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            food_name TEXT NOT NULL,
            calories INTEGER NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def record_calories(food_name: str, calories: int):
    conn = sqlite3.connect('calories.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO calories (food_name, calories) VALUES (?, ?)
    ''', (food_name, calories))
    conn.commit()
    conn.close()
    print(f"记录热量: {food_name} - {calories} 千卡")

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
            {"role": "user", "content": [{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}", "detail": "low"}}]},
        ],
        tools=tools,
    )

    print(response.choices[0].message)

    # Check if the response includes a tool call
    if hasattr(response.choices[0].message, 'tool_calls') and response.choices[0].message.tool_calls:
        for tool_call in response.choices[0].message.tool_calls:
            if tool_call.function.name == 'record_calories':
                # Parse the JSON string in the arguments
                import json
                params = json.loads(tool_call.function.arguments)
                record_calories(params['food_name'], params['calories'])

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
    init_db()
    app.run(host='0.0.0.0', debug=True, ssl_context='adhoc')
