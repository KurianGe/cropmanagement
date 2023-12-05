from decimal import Decimal
import json
import uuid
from flask import Flask, render_template, request, redirect, url_for, flash
import requests
import secrets
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
import boto3
from crop_helper import calculate_total_crops
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(16)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db' 
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

# API endpoint URL
API_ENDPOINT = "https://yb4ct8dsp0.execute-api.eu-west-1.amazonaws.com/Stage1"

response = requests.get(API_ENDPOINT, headers={'Content-Type': 'application/json'})
crops = response.json()

print(crops)

# Your SES region
SES_REGION = 'eu-west-1'  # AWS region

# S3 configurations
S3_BUCKET_NAME = 'x22191437'  #S3 bucket name
s3 = boto3.client('s3')

def get_s3_image_url(crop_id):
    return f'https://{S3_BUCKET_NAME}.s3.amazonaws.com/crop_images/{crop_id}.jpg'

def send_email(subject, body, recipient):
    # Set up SES client
    ses = boto3.client('ses', region_name=SES_REGION)

    # Create MIME message
    message = MIMEMultipart()
    message['Subject'] = subject
    message.attach(MIMEText(body, 'plain'))

    # Send email
    ses.send_raw_email(
        Source='kuriangeorge282@gmail.com',  
        Destinations=[recipient],
        RawMessage={'Data': message.as_string()}
    )

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)

    def __repr__(self):
        return f'<User {self.username}>'

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']

        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        new_user = User(username=username, email=email, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()

        flash('Account created successfully!', 'success')
        return redirect(url_for('signin'))

    return render_template('signup.html')

@app.route('/add_crop_page')
def add_crop_page():
    return render_template('addcrop.html')

@app.route('/signin', methods=['GET', 'POST'])
def signin():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        user = User.query.filter_by(email=email).first()
        if user and bcrypt.check_password_hash(user.password, password):
            flash('Login successful!', 'success')
            # Redirect to the new page for adding crop
            return redirect(url_for('add_crop_page'))
        else:
            flash('Invalid email or password. Please try again.', 'danger')

    return render_template('signin.html')

@app.route('/showcrop', methods=['GET'])
def showcrop():
    try:
        # Fetch all cropes details from DynamoDB
        payload = {'action': 'listcrops'}
        response = requests.get(API_ENDPOINT, json=payload)

        if response.status_code == 200:
            # Parse the JSON response
            allcrops = json.loads(response.json()['body'])

            print("crops Data:", allcrops)  
            
            total_crops = calculate_total_crops(allcrops)
  

            return render_template('showcrop.html', allcrops=allcrops, total_crops=total_crops)
        
        else:
            print(f"Error fetching data from DynamoDB: {response.status_code}")
            return f"Error fetching data from DynamoDB: {response.status_code}"

    except Exception as e:
        print(f"Error: {str(e)}")
        return f"Error: {str(e)}"


@app.route('/delete_crop/<string:crop_id>', methods=['GET'])    # Invoke Lambda function to delete crop
def delete_crop(crop_id):
    try:
        
        payload = {
            'action': 'deletecrop',
            'crop_id': crop_id
        }
        response = requests.post(API_ENDPOINT, json=payload)
        response.raise_for_status()

        flash('crop deleted successfully!', 'success')
        return redirect(url_for('showcrop'))

    except Exception as e:
        flash(f"Error deleting crop: {str(e)}", 'danger')
        return redirect(url_for('showcrop'))

@app.route('/addcrop', methods=['POST'])
def addcrop():
    # Retrieve product details from the form
    crop_name = request.form['crop_name']
    yield_quantity = request.form['yield_quantity']
    harvest_date = request.form['harvest_date']
   

    try:
        # Invoking the Lambda function to add the new crop to DynamoDB
        crop_id = str(uuid.uuid4())  # Generate a unique crop_id, you can use your own logic here
        payload = {
            'action': 'addcrop',
            'crop_id': crop_id,
            'crop_name': crop_name,
            'yield_quantity': yield_quantity,
            'harvest_date': harvest_date,
        }
        response = requests.post(API_ENDPOINT, json=payload)
        response.raise_for_status()  # Raise an HTTPError for bad responses

        crop_id = payload['crop_id']
        crop_details_response = requests.get(API_ENDPOINT, json={'action': 'getcrop', 'crop_id': crop_id})
        crop_details = crop_details_response.json()

        return redirect(url_for('show_added_crop', crop_name=crop_name, yield_quantity=yield_quantity, harvest_date=harvest_date))

    except Exception as e:
        print(f"Error placing order from cart: {str(e)}")
        return render_template('index.html', error=f"Error placing order from cart: {str(e)}")

@app.route('/show_added_crop')
def show_added_crop():
    crop_name = request.args.get('crop_name')
    yield_quantity = request.args.get('yield_quantity')
    harvest_date = request.args.get('harvest_date')

    return render_template('show_added_crop.html', crop_name=crop_name, yield_quantity=yield_quantity, harvest_date=harvest_date)

@app.route('/crop_detail/<string:crop_id>', methods=['GET'])
def crop_detail(crop_id):
    try:
        
        response = requests.get(API_ENDPOINT, json={'action': 'getcrop', 'crop_id': crop_id})
        
        print("crop Detail Response:", response.content)  

        if response.status_code == 200:
             
            crop = response.json()
            return render_template('crop_detail.html', crop=crop)
        else:
            flash('Error fetching crop details from the API', 'danger')
            return redirect(url_for('index'))

    except Exception as e:
        flash(f"Error: {str(e)}", 'danger')
        return redirect(url_for('index'))
    
@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)
