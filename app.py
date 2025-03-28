from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime
from flask_mail import Mail, Message
from dotenv import load_dotenv
import os
import hashlib

# Load environment variables from .env file
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your_secure_secret_key_here')
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Limit file uploads to 16MB

# MongoDB setup
client = MongoClient(os.getenv('MONGO_URI', 'mongodb://localhost:27017/'))
db = client.image_catalog

# Flask-Mail configuration
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True') == 'True'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
mail = Mail(app)

# Helper functions
def hash_password(password):
    """Hash password using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()

def get_user_images(user_id=None, search_query=None, location_query=None):
    """Get images for a specific user or all images, with optional search and location filters."""
    query = {}
    if user_id:
        query['user_id'] = user_id
    if search_query:
        query['name'] = {'$regex': search_query, '$options': 'i'}  # Case-insensitive search by name
    if location_query:
        query['location'] = {'$regex': location_query, '$options': 'i'}  # Case-insensitive search by location
    return list(db.images.find(query).sort('upload_date', -1))

def get_current_user():
    """Retrieve the current user from session."""
    if 'user_id' in session:
        user = db.users.find_one({'_id': ObjectId(session['user_id'])})
        return user
    return None

# Routes
@app.route('/', methods=['GET'])
def index():
    search_query = request.args.get('search', '').strip()
    location_query = request.args.get('location', '').strip()
    images = get_user_images(search_query=search_query, location_query=location_query)
    return render_template('index.html', images=images, current_user=get_current_user(), search_query=search_query, location_query=location_query)

@app.route('/my-images')
def my_images():
    """Page showing only the current user's images."""
    if 'user_id' not in session:
        flash('Please log in to view your images.', 'error')
        return redirect('/login')
    images = get_user_images(session['user_id'])
    return render_template('my_images.html', images=images, current_user=get_current_user())

@app.route('/my-properties')
def my_properties():
    """Page showing only the current user's properties."""
    if 'user_id' not in session:
        flash('Please log in to view your properties.', 'error')
        return redirect('/login')
    images = get_user_images(session['user_id'])
    for img in images:
        img['formatted_date'] = img['upload_date'].strftime('%Y-%m-%d')
    return render_template('property.html', images=images, current_user=get_current_user())

@app.route('/image/<image_id>')
def image_detail(image_id):
    try:
        image = db.images.find_one({'_id': ObjectId(image_id)})
        if image:
            image['formatted_date'] = image['upload_date'].strftime("%Y-%m-%d")
            return render_template('image_details.html', image=image, current_user=get_current_user())
        flash('Image not found', 'error')
        return redirect('/')
    except Exception as e:
        flash(f'Invalid image ID: {str(e)}', 'error')
        return redirect('/')

@app.route('/insert', methods=['GET', 'POST'])
def insert():
    """Upload new properties with location."""
    if 'user_id' not in session:
        flash('Please log in to upload properties.', 'error')
        return redirect('/login')

    if request.method == 'POST':
        try:
            files = request.files.getlist('image')
            if not files or all(file.filename == '' for file in files):
                flash('No files selected', 'error')
                return redirect('/insert')

            image_data_list = []
            for file in files:
                if file and file.filename:
                    filename = secure_filename(file.filename)
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(file_path)

                    image_data = {
                        'name': request.form['name'],
                        'description': request.form['description'],
                        'location': request.form['location'],  # New location field
                        'filename': filename,
                        'upload_date': datetime.utcnow(),
                        'user_id': session['user_id'],
                        'contact_name': request.form['contact_name'],
                        'contact_email': request.form['contact_email'],
                        'contact_phone': request.form['contact_phone']
                    }
                    image_data_list.append(image_data)

            db.images.insert_many(image_data_list)
            flash('Properties uploaded successfully!', 'success')
            return redirect('/my-properties')
        except Exception as e:
            flash(f'Error uploading properties: {str(e)}', 'error')
            return redirect('/insert')
    return render_template('insert.html', current_user=get_current_user())

@app.route('/edit-image/<image_id>', methods=['GET', 'POST'])
def edit_image(image_id):
    """Edit an existing property with location."""
    if 'user_id' not in session:
        flash('Please log in to edit properties.', 'error')
        return redirect('/login')

    try:
        image = db.images.find_one({'_id': ObjectId(image_id), 'user_id': session['user_id']})
        if not image:
            flash('Property not found or you are not authorized to edit it.', 'error')
            return redirect('/my-properties')

        if request.method == 'POST':
            update_data = {
                'name': request.form['name'],
                'description': request.form['description'],
                'location': request.form['location'],  # New location field
                'upload_date': datetime.utcnow(),
                'contact_name': request.form['contact_name'],
                'contact_email': request.form['contact_email'],
                'contact_phone': request.form['contact_phone']
            }

            if 'image' in request.files and request.files['image'].filename:
                file = request.files['image']
                old_file = os.path.join(app.config['UPLOAD_FOLDER'], image['filename'])
                if os.path.exists(old_file):
                    os.remove(old_file)
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                update_data['filename'] = filename

            db.images.update_one({'_id': ObjectId(image_id)}, {'$set': update_data})
            flash('Property updated successfully!', 'success')
            return redirect('/my-properties')

        return render_template('insert.html', image=image, current_user=get_current_user())
    except Exception as e:
        flash(f'Error editing property: {str(e)}', 'error')
        return redirect('/my-properties')

@app.route('/delete-image/<image_id>')
def delete_image(image_id):
    """Delete a property."""
    if 'user_id' not in session:
        flash('Please log in to delete properties.', 'error')
        return redirect('/login')

    try:
        image = db.images.find_one({'_id': ObjectId(image_id), 'user_id': session['user_id']})
        if image:
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], image['filename'])
            if os.path.exists(file_path):
                os.remove(file_path)
            db.images.delete_one({'_id': ObjectId(image_id)})
            flash('Property deleted successfully!', 'success')
        else:
            flash('Property not found or unauthorized', 'error')
    except Exception as e:
        flash(f'Error deleting property: {str(e)}', 'error')
    return redirect('/my-properties')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login."""
    if 'user_id' in session:
        return redirect('/')

    if request.method == 'POST':
        user = db.users.find_one({'email': request.form['email']})
        if user and user['password'] == hash_password(request.form['password']):
            session['user_id'] = str(user['_id'])
            flash('Logged in successfully!', 'success')
            return redirect('/')
        flash('Invalid email or password', 'error')
    return render_template('login.html', current_user=get_current_user())

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    """User signup."""
    if 'user_id' in session:
        return redirect('/')

    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        if db.users.find_one({'email': email}):
            flash('Email already exists', 'error')
            return redirect('/signup')

        user = {
            'email': email,
            'password': hash_password(password),
            'created_at': datetime.utcnow()
        }
        result = db.users.insert_one(user)
        session['user_id'] = str(result.inserted_id)
        flash('Account created successfully!', 'success')
        return redirect('/')
    return render_template('signup.html', current_user=get_current_user())

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    """Contact form submission."""
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        message = request.form.get('message')

        db.contacts.insert_one({
            'name': name,
            'email': email,
            'message': message,
            'submitted_at': datetime.utcnow()
        })

        try:
            msg = Message(
                subject=f"New Contact Form Submission from {name}",
                sender=app.config['MAIL_USERNAME'],
                recipients=[os.getenv('CONTACT_EMAIL', 'yogesh.chauhan.ai@gmail.com')],
                body=f"Name: {name}\nEmail: {email}\nMessage: {message}"
            )
            mail.send(msg)
            flash('Your message has been sent successfully!', 'success')
        except Exception as e:
            flash(f'Failed to send email: {str(e)}', 'error')
        return redirect('/contact')
    return render_template('contact.html', current_user=get_current_user())

@app.route('/about')
def about():
    """About page."""
    current_year = datetime.now().year
    return render_template('about.html', current_year=current_year, current_user=get_current_user())

@app.route('/logout')
def logout():
    """User logout."""
    session.pop('user_id', None)
    flash('Logged out successfully!', 'success')
    return redirect('/')

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(debug=True, host='0.0.0.0', port=5000)