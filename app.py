from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime
from flask_mail import Mail, Message
from datetime import datetime, timedelta 
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

# Admin credentials (in practice, store these in environment variables or database)
ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', 'admin@example.com')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin123')  # Hashed in production

# Helper functions
def hash_password(password):
    """Hash password using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()

def get_user_images(user_id=None, search_query=None, location_query=None, approved_only=True):
    """Get images with optional filters."""
    query = {}
    if user_id:
        query['user_id'] = user_id
    if search_query:
        query['name'] = {'$regex': search_query, '$options': 'i'}
    if location_query:
        query['location'] = {'$regex': location_query, '$options': 'i'}
    if approved_only:
        query['status'] = 'approved'
    return list(db.images.find(query).sort('upload_date', -1))

def get_current_user():
    """Retrieve the current user from session."""
    if 'user_id' in session:
        user = db.users.find_one({'_id': ObjectId(session['user_id'])})
        return user
    return None

def is_admin():
    """Check if current session is admin."""
    return 'admin' in session and session['admin'] == True

# Routes
@app.route('/', methods=['GET'])
def index():
    search_query = request.args.get('search', '').strip()
    location_query = request.args.get('location', '').strip()
    images = get_user_images(search_query=search_query, location_query=location_query)
    return render_template('index.html', images=images, current_user=get_current_user())

@app.route('/my-images')
def my_images():
    if 'user_id' not in session:
        flash('Please log in to view your images.', 'error')
        return redirect('/login')
    images = get_user_images(session['user_id'], approved_only=False)
    return render_template('my_images.html', images=images, current_user=get_current_user())

@app.route('/my-properties')
def my_properties():
    if 'user_id' not in session:
        flash('Please log in to view your properties.', 'error')
        return redirect('/login')
    images = get_user_images(session['user_id'], approved_only=False)
    for img in images:
        img['formatted_date'] = img['upload_date'].strftime('%Y-%m-%d')
    return render_template('property.html', images=images, current_user=get_current_user())

@app.route('/image/<image_id>')
def image_detail(image_id):
    try:
        image = db.images.find_one({'_id': ObjectId(image_id), 'status': 'approved'})
        if image:
            image['formatted_date'] = image['upload_date'].strftime("%Y-%m-%d")
            return render_template('image_details.html', image=image, current_user=get_current_user())
        flash('Image not found or not approved', 'error')
        return redirect('/')
    except Exception as e:
        flash(f'Invalid image ID: {str(e)}', 'error')
        return redirect('/')

@app.route('/insert', methods=['GET', 'POST'])
def insert():
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
                        'location': request.form['location'],
                        'filename': filename,
                        'upload_date': datetime.utcnow(),
                        'user_id': session['user_id'],
                        'contact_name': request.form['contact_name'],
                        'contact_email': request.form['contact_email'],
                        'contact_phone': request.form['contact_phone'],
                        'status': 'pending'  # New property starts as pending
                    }
                    image_data_list.append(image_data)

            db.images.insert_many(image_data_list)
            flash('Properties submitted for approval!', 'success')
            return redirect('/my-properties')
        except Exception as e:
            flash(f'Error uploading properties: {str(e)}', 'error')
            return redirect('/insert')
    
    # For GET requests, pass image=None since we're creating a new property
    return render_template('insert.html', image=None, current_user=get_current_user())

# Admin Routes
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if is_admin():
        return redirect('/admin')
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:  # In production, use hashed password
            session['admin'] = True
            flash('Admin logged in successfully!', 'success')
            return redirect('/admin')  # Redirect to admin panel after login
        else:
            flash('Invalid admin credentials', 'error')
            return render_template('admin_login.html')  # Stay on login page if credentials are wrong
    return render_template('admin_login.html')

@app.route('/admin')
def admin_panel():
    if not is_admin():
        flash('Admin access required', 'error')
        return redirect('/admin/login')
    
    # Get pending properties
    pending_properties = list(db.images.find({'status': 'pending'}).sort('upload_date', -1))
    for prop in pending_properties:
        prop['formatted_date'] = prop['upload_date'].strftime('%Y-%m-%d')
    
    # Calculate statistics
    stats = {
        'approved_count': db.images.count_documents({'status': 'approved'}),
        'pending_count': db.images.count_documents({'status': 'pending'}),
        'rejected_count': db.images.count_documents({'status': 'rejected'}),
        'user_count': db.users.count_documents({})
    }
    
    return render_template('admin_panel.html', 
                         properties=pending_properties,
                         stats=stats)

@app.route('/admin/approve/<image_id>')
def approve_property(image_id):
    if not is_admin():
        flash('Admin access required', 'error')
        return redirect('/admin/login')
    
    try:
        db.images.update_one(
            {'_id': ObjectId(image_id)},
            {'$set': {'status': 'approved'}}
        )
        flash('Property approved successfully!', 'success')
    except Exception as e:
        flash(f'Error approving property: {str(e)}', 'error')
    return redirect('/admin')

@app.route('/admin/reject/<image_id>')
def reject_property(image_id):
    if not is_admin():
        flash('Admin access required', 'error')
        return redirect('/admin/login')
    
    try:
        image = db.images.find_one({'_id': ObjectId(image_id)})
        if image:
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], image['filename'])
            if os.path.exists(file_path):
                os.remove(file_path)
            db.images.delete_one({'_id': ObjectId(image_id)})
            flash('Property rejected and deleted!', 'success')
    except Exception as e:
        flash(f'Error rejecting property: {str(e)}', 'error')
    return redirect('/admin')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    flash('Admin logged out successfully!', 'success')
    return redirect('/admin/login')

# Existing routes (modified where necessary)
@app.route('/edit-image/<image_id>', methods=['GET', 'POST'])
def edit_image(image_id):
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
                'location': request.form['location'],
                'upload_date': datetime.utcnow(),
                'contact_name': request.form['contact_name'],
                'contact_email': request.form['contact_email'],
                'contact_phone': request.form['contact_phone'],
                'status': 'pending'  # Edited properties need re-approval
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
            flash('Property updated and submitted for re-approval!', 'success')
            return redirect('/my-properties')

        return render_template('insert.html', image=image, current_user=get_current_user())
    except Exception as e:
        flash(f'Error editing property: {str(e)}', 'error')
        return redirect('/my-properties')

@app.route('/delete-image/<image_id>')
def delete_image(image_id):
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
# Add these routes to your existing Flask app

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        user = db.users.find_one({'email': email})
        
        if user:
            # Generate reset token
            token = str(ObjectId())
            reset_expires = datetime.utcnow() + timedelta(hours=1)
            
            # Store token in database
            db.password_resets.insert_one({
                'user_id': user['_id'],
                'token': token,
                'expires_at': reset_expires,
                'used': False
            })
            
            # Send email with reset link
            reset_link = url_for('reset_password', token=token, _external=True)
            
            try:
                msg = Message(
                    subject="Password Reset Request",
                    sender=app.config['MAIL_USERNAME'],
                    recipients=[email],
                    body=f"""You requested a password reset for your account.
                    
Please click the following link to reset your password:
{reset_link}

This link will expire in 1 hour.

If you didn't request this, please ignore this email.""",
                    html=f"""<p>You requested a password reset for your account.</p>
<p>Please click the following link to reset your password:</p>
<p><a href="{reset_link}">{reset_link}</a></p>
<p>This link will expire in 1 hour.</p>
<p>If you didn't request this, please ignore this email.</p>"""
                )
                mail.send(msg)
                flash('Password reset link has been sent to your email', 'success')
            except Exception as e:
                flash('Failed to send reset email. Please try again.', 'error')
                app.logger.error(f"Failed to send reset email: {str(e)}")
        else:
            # For security, don't reveal if the email exists
            flash('If this email exists in our system, a reset link has been sent', 'success')
        
        return redirect(url_for('forgot_password'))
    
    return render_template('forgot_password.html', current_user=get_current_user())

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    # Find valid reset token
    reset_request = db.password_resets.find_one({
        'token': token,
        'used': False,
        'expires_at': {'$gt': datetime.utcnow()}
    })
    
    if not reset_request:
        flash('Invalid or expired reset link', 'error')
        return redirect(url_for('forgot_password'))
    
    if request.method == 'POST':
        new_password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if new_password != confirm_password:
            flash('Passwords do not match', 'error')
            return redirect(url_for('reset_password', token=token))
        
        # Update password
        db.users.update_one(
            {'_id': reset_request['user_id']},
            {'$set': {'password': hash_password(new_password)}}
        )
        
        # Mark token as used
        db.password_resets.update_one(
            {'_id': reset_request['_id']},
            {'$set': {'used': True}}
        )
        
        flash('Password updated successfully. You can now login with your new password.', 'success')
        return redirect(url_for('login'))
    
    return render_template('reset_password.html', token=token, current_user=get_current_user())

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