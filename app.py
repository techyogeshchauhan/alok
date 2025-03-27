from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime
from flask_mail import Mail, Message
from dotenv import load_dotenv
import os
import hashlib

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your_secure_secret_key_here')  # Load from .env or use default
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

# Initialize Flask-Mail
mail = Mail(app)

# Helper functions
def hash_password(password):
    """Hash password using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()

def get_user_images(user_id=None):
    """Get images for a specific user or all images if no user_id is provided."""
    query = {'user_id': user_id} if user_id else {}
    return list(db.images.find(query).sort('upload_date', -1))

def get_current_user():
    """Retrieve the current user from session."""
    if 'user_id' in session:
        user = db.users.find_one({'_id': ObjectId(session['user_id'])})
        return user
    return None

# Routes
@app.route('/')
def index():
    images = get_user_images()  # Show all images on home page
    return render_template('index.html', images=images, current_user=get_current_user())

@app.route('/my-images')
def my_images():
    if 'user_id' not in session:
        flash('Please log in to view your images.', 'error')
        return redirect('/login')
    images = get_user_images(session['user_id'])
    return render_template('my_images.html', images=images, current_user=get_current_user())

@app.route('/my-properties')
def my_properties():
    if 'user_id' not in session:
        flash('Please log in to view your properties.', 'error')
        return redirect('/login')
    images = get_user_images(session['user_id'])  # Using same collection as my-images for now
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
    if 'user_id' not in session:
        flash('Please log in to upload images.', 'error')
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
                        'filename': filename,
                        'upload_date': datetime.utcnow(),
                        'user_id': session['user_id'],
                        'contact_name': request.form['contact_name'],
                        'contact_email': request.form['contact_email'],
                        'contact_phone': request.form['contact_phone']
                    }
                    image_data_list.append(image_data)

            db.images.insert_many(image_data_list)
            flash('Images uploaded successfully!', 'success')
            return redirect('/my-images')
        except Exception as e:
            flash(f'Error uploading images: {str(e)}', 'error')
            return redirect('/insert')
    return render_template('insert.html', current_user=get_current_user())

@app.route('/edit-image/<image_id>', methods=['GET', 'POST'])
def edit_image(image_id):
    if 'user_id' not in session:
        flash('Please log in to edit images.', 'error')
        return redirect('/login')

    try:
        image = db.images.find_one({'_id': ObjectId(image_id), 'user_id': session['user_id']})
        if not image:
            flash('Image not found or you are not authorized to edit it.', 'error')
            return redirect('/my-images')

        if request.method == 'POST':
            update_data = {
                'name': request.form['name'],
                'description': request.form['description'],
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
            flash('Image updated successfully!', 'success')
            return redirect('/my-images')

        return render_template('insert.html', image=image, current_user=get_current_user())
    except Exception as e:
        flash(f'Error editing image: {str(e)}', 'error')
        return redirect('/my-images')

@app.route('/delete-image/<image_id>')
def delete_image(image_id):
    if 'user_id' not in session:
        flash('Please log in to delete images.', 'error')
        return redirect('/login')

    try:
        image = db.images.find_one({'_id': ObjectId(image_id), 'user_id': session['user_id']})
        if image:
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], image['filename'])
            if os.path.exists(file_path):
                os.remove(file_path)
            db.images.delete_one({'_id': ObjectId(image_id)})
            flash('Image deleted successfully!', 'success')
        else:
            flash('Image not found or unauthorized', 'error')
    except Exception as e:
        flash(f'Error deleting image: {str(e)}', 'error')
    return redirect('/my-images')

@app.route('/login', methods=['GET', 'POST'])
def login():
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
            'password': hash_password(password),  # Hash password before storing
            'created_at': datetime.utcnow()
        }
        result = db.users.insert_one(user)
        session['user_id'] = str(result.inserted_id)
        flash('Account created successfully!', 'success')
        return redirect('/')
    return render_template('signup.html', current_user=get_current_user())

@app.route('/contact', methods=['GET', 'POST'])
def contact():
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
    current_year = datetime.now().year
    return render_template('about.html', current_year=current_year, current_user=get_current_user())

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('Logged out successfully!', 'success')
    return redirect('/')

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(debug=True, host='0.0.0.0', port=5000)