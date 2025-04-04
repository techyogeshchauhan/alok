from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, make_response
from werkzeug.utils import secure_filename
from pymongo import MongoClient
from gridfs import GridFS
from bson.objectid import ObjectId
from datetime import datetime, timedelta
from flask_mail import Mail, Message
from dotenv import load_dotenv
import os
import hashlib
import io
from PIL import Image
import logging
from logging.handlers import RotatingFileHandler

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', os.urandom(24))
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB upload limit
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# Configure logging
handler = RotatingFileHandler('app.log', maxBytes=10000, backupCount=3)
handler.setLevel(logging.INFO)
app.logger.addHandler(handler)

# MongoDB setup with enhanced error handling
try:
    MONGO_URI = os.getenv('MONGO_URI', "mongodb://localhost:27017/image_catalog")
    client = MongoClient(
        MONGO_URI,
        connectTimeoutMS=30000,
        socketTimeoutMS=30000,
        serverSelectionTimeoutMS=5000
    )
    # Test the connection
    client.admin.command('ping')
    db = client.get_database()
    fs = GridFS(db)
    app.logger.info("Successfully connected to MongoDB")
except Exception as e:
    app.logger.error(f"Could not connect to MongoDB: {str(e)}")
    raise

# Flask-Mail configuration with fallback
mail_settings = {
    'MAIL_SERVER': os.getenv('MAIL_SERVER', 'smtp.gmail.com'),
    'MAIL_PORT': int(os.getenv('MAIL_PORT', 587)),
    'MAIL_USE_TLS': os.getenv('MAIL_USE_TLS', 'True') == 'True',
    'MAIL_USERNAME': os.getenv('MAIL_USERNAME'),
    'MAIL_PASSWORD': os.getenv('MAIL_PASSWORD'),
    'MAIL_DEFAULT_SENDER': os.getenv('MAIL_DEFAULT_SENDER', 'noreply@example.com')
}
app.config.update(mail_settings)
mail = Mail(app)

# Admin credentials - consider using a proper admin collection in DB
ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', 'admin@example.com')
ADMIN_PASSWORD_HASH = hashlib.sha256(os.getenv('ADMIN_PASSWORD', 'admin123').encode()).hexdigest()

# Helper functions
def hash_password(password):
    """Secure password hashing with salt"""
    salt = os.urandom(16).hex()
    return hashlib.sha256((password + salt).encode()).hexdigest() + ':' + salt

def verify_password(stored_password, provided_password):
    """Verify a password against stored hash"""
    if ':' not in stored_password:
        return False
    hashed, salt = stored_password.split(':')
    return hashed == hashlib.sha256((provided_password + salt).encode()).hexdigest()

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def resize_image(file_stream, max_size=(1200, 1200), quality=85):
    """Resize image while maintaining aspect ratio"""
    try:
        img = Image.open(file_stream)
        if img.mode != 'RGB':
            img = img.convert('RGB')
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        img_io = io.BytesIO()
        img.save(img_io, 'JPEG', quality=quality, optimize=True)
        img_io.seek(0)
        return img_io
    except Exception as e:
        app.logger.error(f"Error resizing image: {str(e)}")
        raise

def get_user_images(user_id=None, search_query=None, location_query=None, approved_only=True):
    """Query images with optional filters"""
    query = {}
    if user_id:
        query['user_id'] = ObjectId(user_id)
    if search_query:
        query['$or'] = [
            {'name': {'$regex': search_query, '$options': 'i'}},
            {'description': {'$regex': search_query, '$options': 'i'}}
        ]
    if location_query:
        query['location'] = {'$regex': location_query, '$options': 'i'}
    if approved_only:
        query['status'] = 'approved'
    
    try:
        images = list(db.images.find(query).sort('upload_date', -1))
        for img in images:
            img['id'] = str(img['_id'])  # Convert ObjectId to string for templates
            img['formatted_date'] = img['upload_date'].strftime('%Y-%m-%d')
        return images
    except Exception as e:
        app.logger.error(f"Error fetching images: {str(e)}")
        return []

def get_current_user():
    """Get current user from session"""
    if 'user_id' in session:
        try:
            return db.users.find_one({'_id': ObjectId(session['user_id'])})
        except:
            session.pop('user_id', None)
    return None

def is_admin():
    """Check if current user is admin"""
    if 'admin_id' in session:
        try:
            admin = db.users.find_one({'_id': ObjectId(session['admin_id']), 'is_admin': True})
            return admin is not None
        except:
            session.pop('admin_id', None)
    return False

def login_required(f):
    """Decorator for routes that require login"""
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Decorator for admin-only routes"""
    def decorated_function(*args, **kwargs):
        if not is_admin():
            flash('Admin access required', 'error')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# Routes
@app.route('/', methods=['GET'])
def index():
    try:
        search_query = request.args.get('search', '').strip()
        location_query = request.args.get('location', '').strip()
        images = get_user_images(search_query=search_query, location_query=location_query)
        return render_template('index.html', 
                             images=images, 
                             current_user=get_current_user(),
                             search_query=search_query,
                             location_query=location_query)
    except Exception as e:
        app.logger.error(f"Error in index route: {str(e)}")
        flash('An error occurred while loading properties', 'error')
        return render_template('index.html', images=[], current_user=get_current_user())

@app.route('/my-images')
@login_required
def my_images():
    try:
        images = get_user_images(session['user_id'], approved_only=False)
        return render_template('my_images.html', 
                             images=images, 
                             current_user=get_current_user())
    except Exception as e:
        app.logger.error(f"Error in my_images route: {str(e)}")
        flash('An error occurred while loading your images', 'error')
        return redirect(url_for('index'))

@app.route('/my-properties')
@login_required
def my_properties():
    try:
        images = get_user_images(session['user_id'], approved_only=False)
        return render_template('property.html', 
                             images=images, 
                             current_user=get_current_user())
    except Exception as e:
        app.logger.error(f"Error in my_properties route: {str(e)}")
        flash('An error occurred while loading your properties', 'error')
        return redirect(url_for('index'))

@app.route('/image/<image_id>')
def image_detail(image_id):
    try:
        image = db.images.find_one({'_id': ObjectId(image_id), 'status': 'approved'})
        if not image:
            flash('Image not found or not approved', 'error')
            return redirect(url_for('index'))
        
        image['formatted_date'] = image['upload_date'].strftime("%Y-%m-%d")
        return render_template('image_details.html', 
                            image=image, 
                            current_user=get_current_user())
    except Exception as e:
        app.logger.error(f"Error in image_detail route: {str(e)}")
        flash('Invalid image ID', 'error')
        return redirect(url_for('index'))

@app.route('/insert', methods=['GET', 'POST'])
@login_required
def insert():
    if request.method == 'GET':
        return render_template('insert.html', 
                             image=None, 
                             current_user=get_current_user())
    
    try:
        files = request.files.getlist('image')
        if not files or all(file.filename == '' for file in files):
            flash('No files selected', 'error')
            return redirect(url_for('insert'))
        
        image_data_list = []
        for file in files:
            if file and file.filename:
                if not allowed_file(file.filename):
                    flash(f'File {file.filename} has invalid extension', 'error')
                    continue
                
                filename = secure_filename(file.filename)
                try:
                    img_io = resize_image(file.stream)
                    file_id = fs.put(img_io, filename=filename)
                    
                    image_data = {
                        'name': request.form.get('name', 'Untitled'),
                        'description': request.form.get('description', ''),
                        'location': request.form.get('location', 'Unknown'),
                        'file_id': str(file_id),
                        'upload_date': datetime.utcnow(),
                        'user_id': ObjectId(session['user_id']),
                        'contact_name': request.form.get('contact_name', ''),
                        'contact_email': request.form.get('contact_email', ''),
                        'contact_phone': request.form.get('contact_phone', ''),
                        'status': 'pending'
                    }
                    image_data_list.append(image_data)
                except Exception as e:
                    app.logger.error(f"Error processing file {filename}: {str(e)}")
                    flash(f'Error processing {filename}', 'error')
        
        if image_data_list:
            db.images.insert_many(image_data_list)
            flash(f'{len(image_data_list)} properties submitted for approval!', 'success')
        return redirect(url_for('my_properties'))
    
    except Exception as e:
        app.logger.error(f"Error in insert route: {str(e)}")
        flash('Error uploading properties', 'error')
        return redirect(url_for('insert'))

@app.route('/serve-image/<file_id>')
def serve_image(file_id):
    try:
        if not ObjectId.is_valid(file_id):
            return send_file('static/images/placeholder.jpg', mimetype='image/jpeg')
            
        grid_out = fs.get(ObjectId(file_id))
        response = make_response(grid_out.read())
        response.headers.set('Content-Type', 'image/jpeg')
        response.headers.set('Cache-Control', 'public, max-age=31536000')  # 1 year cache
        return response
    except Exception as e:
        app.logger.error(f"Error serving image {file_id}: {str(e)}")
        return send_file('static/images/placeholder.jpg', mimetype='image/jpeg')

@app.route('/edit-image/<image_id>', methods=['GET', 'POST'])
@login_required
def edit_image(image_id):
    try:
        image = db.images.find_one({'_id': ObjectId(image_id), 'user_id': ObjectId(session['user_id'])})
        if not image:
            flash('Property not found or unauthorized', 'error')
            return redirect(url_for('my_properties'))
        
        if request.method == 'GET':
            return render_template('insert.html', 
                                 image=image, 
                                 current_user=get_current_user())
        
        # Handle POST request
        update_data = {
            'name': request.form.get('name', image.get('name', '')),
            'description': request.form.get('description', image.get('description', '')),
            'location': request.form.get('location', image.get('location', '')),
            'contact_name': request.form.get('contact_name', image.get('contact_name', '')),
            'contact_email': request.form.get('contact_email', image.get('contact_email', '')),
            'contact_phone': request.form.get('contact_phone', image.get('contact_phone', '')),
            'status': 'pending',  # Needs re-approval
            'updated_at': datetime.utcnow()
        }
        
        if 'image' in request.files and request.files['image'].filename:
            file = request.files['image']
            if allowed_file(file.filename):
                try:
                    img_io = resize_image(file.stream)
                    # Delete old file from GridFS
                    fs.delete(ObjectId(image['file_id']))
                    # Store new file
                    file_id = fs.put(img_io, filename=secure_filename(file.filename))
                    update_data['file_id'] = str(file_id)
                except Exception as e:
                    app.logger.error(f"Error updating image: {str(e)}")
                    flash('Error updating image', 'error')
        
        db.images.update_one({'_id': ObjectId(image_id)}, {'$set': update_data})
        flash('Property updated and submitted for re-approval!', 'success')
        return redirect(url_for('my_properties'))
    
    except Exception as e:
        app.logger.error(f"Error in edit_image route: {str(e)}")
        flash('Error editing property', 'error')
        return redirect(url_for('my_properties'))

@app.route('/delete-image/<image_id>')
@login_required
def delete_image(image_id):
    try:
        image = db.images.find_one({'_id': ObjectId(image_id), 'user_id': ObjectId(session['user_id'])})
        if image:
            # Delete from GridFS
            fs.delete(ObjectId(image['file_id']))
            # Delete from images collection
            db.images.delete_one({'_id': ObjectId(image_id)})
            flash('Property deleted successfully!', 'success')
        else:
            flash('Property not found or unauthorized', 'error')
    except Exception as e:
        app.logger.error(f"Error deleting image {image_id}: {str(e)}")
        flash('Error deleting property', 'error')
    return redirect(url_for('my_properties'))

# Authentication routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        try:
            user = db.users.find_one({'email': request.form['email']})
            if user and verify_password(user['password'], request.form['password']):
                session['user_id'] = str(user['_id'])
                if user.get('is_admin', False):
                    session['admin_id'] = str(user['_id'])
                flash('Logged in successfully!', 'success')
                return redirect(request.args.get('next') or url_for('index'))
            flash('Invalid email or password', 'error')
        except Exception as e:
            app.logger.error(f"Login error: {str(e)}")
            flash('Login error occurred', 'error')
    return render_template('login.html', current_user=get_current_user())

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if 'user_id' in session:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        try:
            email = request.form['email']
            password = request.form['password']
            
            if db.users.find_one({'email': email}):
                flash('Email already exists', 'error')
                return redirect(url_for('signup'))
            
            user = {
                'email': email,
                'password': hash_password(password),
                'created_at': datetime.utcnow(),
                'is_admin': False
            }
            result = db.users.insert_one(user)
            session['user_id'] = str(result.inserted_id)
            flash('Account created successfully!', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            app.logger.error(f"Signup error: {str(e)}")
            flash('Error creating account', 'error')
    return render_template('signup.html', current_user=get_current_user())

# Admin routes
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if is_admin():
        return redirect(url_for('admin_panel'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        try:
            admin = db.users.find_one({'email': email, 'is_admin': True})
            if admin and verify_password(admin['password'], password):
                session['admin_id'] = str(admin['_id'])
                flash('Admin logged in successfully!', 'success')
                return redirect(url_for('admin_panel'))
            flash('Invalid admin credentials', 'error')
        except Exception as e:
            app.logger.error(f"Admin login error: {str(e)}")
            flash('Admin login error', 'error')
    return render_template('admin_login.html')

@app.route('/admin')
@admin_required
def admin_panel():
    try:
        pending_properties = list(db.images.find({'status': 'pending'}).sort('upload_date', -1))
        for prop in pending_properties:
            prop['id'] = str(prop['_id'])
            prop['formatted_date'] = prop['upload_date'].strftime('%Y-%m-%d')
        
        stats = {
            'approved_count': db.images.count_documents({'status': 'approved'}),
            'pending_count': db.images.count_documents({'status': 'pending'}),
            'rejected_count': db.images.count_documents({'status': 'rejected'}),
            'user_count': db.users.count_documents({})
        }
        
        return render_template('admin_panel.html', 
                             properties=pending_properties,
                             stats=stats)
    except Exception as e:
        app.logger.error(f"Admin panel error: {str(e)}")
        flash('Error loading admin panel', 'error')
        return redirect(url_for('admin_login'))

@app.route('/admin/approve/<image_id>')
@admin_required
def approve_property(image_id):
    try:
        result = db.images.update_one(
            {'_id': ObjectId(image_id)},
            {'$set': {'status': 'approved', 'approved_at': datetime.utcnow()}}
        )
        if result.modified_count > 0:
            flash('Property approved successfully!', 'success')
        else:
            flash('Property not found or already approved', 'error')
    except Exception as e:
        app.logger.error(f"Approve property error: {str(e)}")
        flash('Error approving property', 'error')
    return redirect(url_for('admin_panel'))

@app.route('/admin/reject/<image_id>')
@admin_required
def reject_property(image_id):
    try:
        image = db.images.find_one({'_id': ObjectId(image_id)})
        if image:
            # Delete from GridFS
            fs.delete(ObjectId(image['file_id']))
            # Delete from images collection
            db.images.delete_one({'_id': ObjectId(image_id)})
            flash('Property rejected!', 'success')
        else:
            flash('Property not found', 'error')
    except Exception as e:
        app.logger.error(f"Reject property error: {str(e)}")
        flash('Error rejecting property', 'error')
    return redirect(url_for('admin_panel'))

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_id', None)
    flash('Admin logged out successfully!', 'success')
    return redirect(url_for('admin_login'))

# Other routes
@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        try:
            contact_data = {
                'name': request.form.get('name', ''),
                'email': request.form.get('email', ''),
                'message': request.form.get('message', ''),
                'submitted_at': datetime.utcnow()
            }
            db.contacts.insert_one(contact_data)
            
            try:
                msg = Message(
                    subject=f"New Contact Form Submission from {contact_data['name']}",
                    sender=app.config['MAIL_DEFAULT_SENDER'],
                    recipients=[os.getenv('CONTACT_EMAIL', 'yogesh.chauhan.ai@gmail.com')],
                    body=f"Name: {contact_data['name']}\nEmail: {contact_data['email']}\nMessage: {contact_data['message']}"
                )
                mail.send(msg)
                flash('Your message has been sent successfully!', 'success')
            except Exception as e:
                app.logger.error(f"Email send error: {str(e)}")
                flash('Message saved but failed to send email notification', 'warning')
        except Exception as e:
            app.logger.error(f"Contact form error: {str(e)}")
            flash('Error submitting message', 'error')
        return redirect(url_for('contact'))
    
    return render_template('contact.html', current_user=get_current_user())

@app.route('/about')
def about():
    current_year = datetime.now().year
    return render_template('about.html', 
                         current_year=current_year, 
                         current_user=get_current_user())

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully!', 'success')
    return redirect(url_for('index'))

# Error handlers
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    app.logger.error(f"500 Error: {str(e)}")
    return render_template('500.html'), 500

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(host='0.0.0.0', port=5000)