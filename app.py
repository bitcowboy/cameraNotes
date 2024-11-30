from flask import Flask, render_template, request, jsonify, redirect, url_for
import os
import uuid
import base64
import json
from openai import OpenAI
import sqlite3
from collections import defaultdict
from datetime import datetime
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from authlib.integrations.flask_client import OAuth

system_prompt = """
你是一个智能助手。你会分析用户拍的照片，并给出分析其中的主题。根据不同的主题，调用相应的工具，帮助用户备忘、记录信息或解决问题。
如果是食物，请告诉我食物的名称和热量，并调用相应的函数做记录。
如果是房号，告诉我房间号码。
如果是小票，请告诉我小票上的信息。
如果是其它信息，请告诉我你认为的信息。

当你检测到主题时直接调用工具，不需要用户确认。
使用简体中文回答。
"""

system_prompt_2 = """
  You are a very useful assistant. Help me with determining the caloric content of products
"""

user_prompt = """
  The photo shows food products for a meal. Determine approximately which products are shown in the photo and return them ONLY as a json list, 
  where each list element should contain:
    * "title" - the name of the product, 
    * "weight" - weight in grams, 
    * "kilocalories_per100g" - how many calories are contained in this product in 100 grams, 
    * "proteins_per100g" - the amount of proteins of this product per 100 grams, 
    * "fats_per100g" - the amount of fat per 100 grams of this product, 
    * "carbohydrates_per100g" - the amount of carbohydrates per 100 grams of this product, 
    * "fiber_per100g" - the amount of fiber per 100 grams of this product, 
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
app.secret_key = 'f540ce17793920d21c2c49b0bb9c51af'

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

with open('oauth_client.json', 'r') as file:
    google_oauth_client = json.load(file)

# Initialize OAuth
oauth = OAuth(app)
google = oauth.register(
    name="google",
    client_id=google_oauth_client['client_id'],
    client_secret=google_oauth_client['client_secret'],
    access_token_url= "https://oauth2.googleapis.com/token",
    authorize_url= "https://accounts.google.com/o/oauth2/v2/auth",
    api_base_url= "https://www.googleapis.com/oauth2/v3/",
    client_kwargs= {"scope": "openid email profile"},
    userinfo_endpoint = 'https://openidconnect.googleapis.com/v1/userinfo',
    server_metadata_url= 'https://accounts.google.com/.well-known/openid-configuration'
)

# User class for Flask-Login
class User(UserMixin):
    def __init__(self, id, name, email):
        self.id = id
        self.name = name
        self.email = email

@login_manager.user_loader
def load_user(user_id):
    # Implement user loading logic here
    return User(user_id, None, None)

@app.route('/login')
def login():
    redirect_uri = url_for('authorize', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/authorize')
def authorize():
    token = google.authorize_access_token()
    resp = google.get('userinfo')
    user_info = resp.json()
    print(user_info)
    user = User(user_info['sub'], user_info['name'], user_info['email'])
    login_user(user)
    return redirect('/')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect('/')

@app.route('/')
@login_required
def index():
    return render_template('index.html', user=current_user)

# Initialize the SQLite database
def init_db():
    conn = sqlite3.connect('calories.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS calories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            food_name TEXT NOT NULL,
            calories INTEGER NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
            image_path TEXT
        )
    ''')
    conn.commit()
    conn.close()

def record_calories(food_name: str, calories: int, image_filename: str):
    conn = sqlite3.connect('calories.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO calories (food_name, calories, image_path) VALUES (?, ?, ?)
    ''', (food_name, calories, image_filename))
    conn.commit()   
    conn.close()
    print(f"记录热量: {food_name} - {calories} 千卡, Image Path: {image_filename}")

# Function to encode the image
def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def analyze_image(unique_filename):
    image_path = os.path.join('static', unique_filename)
    base64_image = encode_image(image_path)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt_2},
            {"role": "user", "content": user_prompt},
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
                record_calories(params['food_name'], params['calories'], unique_filename)

    return response.choices[0].message.content

@app.route('/upload', methods=['POST'])
def upload():
    if 'image' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    # Generate a unique filename with the correct extension
    unique_filename = f"{uuid.uuid4()}.jpg"
    file_path = os.path.join('static', unique_filename)
    file.save(file_path)

    analysis = analyze_image(unique_filename)
    return jsonify({'success': True, 'result': analysis})

@app.route('/list')
def list_foods():
    conn = sqlite3.connect('calories.db')
    cursor = conn.cursor()
    cursor.execute('SELECT food_name, calories, image_path FROM calories')
    foods = cursor.fetchall()
    conn.close()
    return render_template('list.html', foods=foods)

@app.route('/calendar')
def calendar():
    conn = sqlite3.connect('calories.db')
    cursor = conn.cursor()
    cursor.execute('SELECT calories, timestamp FROM calories')
    records = cursor.fetchall()
    conn.close()

    # Calculate total calories per day
    daily_calories = defaultdict(int)
    for calories, timestamp in records:
        date = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S').date()
        daily_calories[date] += calories

    return render_template('calendar.html', daily_calories=daily_calories)

if __name__ == '__main__':
    if not os.path.exists('static'):
        os.makedirs('static')
    init_db()
    app.run(host='0.0.0.0', debug=True, ssl_context='adhoc')
