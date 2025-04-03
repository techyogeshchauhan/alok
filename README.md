# Real Estate Property Listing Website

This is a Flask-based web application for listing, managing, and approving real estate properties. Users can upload property details, and an admin panel allows for approval and management of listings.

## Features
- User authentication (signup, login, logout, password reset)
- Property listing with image upload
- Search and filter properties by name and location
- User dashboard for managing their listings
- Admin dashboard for approving/rejecting properties
- Email notifications for contact forms and password reset requests
- Secure password hashing and session management

## Tech Stack
- **Backend:** Flask, MongoDB
- **Frontend:** HTML, CSS, Bootstrap, Jinja2
- **Database:** MongoDB (via PyMongo)
- **Authentication:** Flask-Session
- **Email Services:** Flask-Mail

## Installation
### Prerequisites
- Python 3.x installed
- MongoDB installed and running

### Setup
1. Clone the repository:
   ```sh
   git clone https://github.com/your-username/real-estate-listing.git
   cd real-estate-listing
   ```
2. Install dependencies:
   ```sh
   pip install -r requirements.txt
   ```
3. Create a `.env` file and add the following variables:
   ```sh
   SECRET_KEY=your_secret_key
   MONGO_URI=mongodb://localhost:27017/your_database
   MAIL_SERVER=smtp.gmail.com
   MAIL_PORT=587
   MAIL_USE_TLS=True
   MAIL_USERNAME=your_email@gmail.com
   MAIL_PASSWORD=your_email_password
   CONTACT_EMAIL=your_contact_email@gmail.com
   ADMIN_EMAIL=admin@example.com
   ADMIN_PASSWORD=admin123
   ```
4. Run the application:
   ```sh
   python app.py
   ```
5. Open your browser and navigate to `http://127.0.0.1:5000`

## Usage
### User Features
- Sign up and log in
- Upload property listings with images and contact details
- View and manage uploaded properties
- Search for properties
- Contact property owners

### Admin Features
- Log in as an admin
- Approve or reject property listings
- Manage all user listings
- View website statistics

## File Structure
```
real-estate-listing/
│-- static/
│   ├── uploads/  # Stores uploaded property images
│-- templates/
│   ├── index.html  # Home page
│   ├── login.html  # User login page
│   ├── signup.html  # User signup page
│   ├── insert.html  # Property upload form
│   ├── admin_panel.html  # Admin dashboard
│   ├── my_images.html  # User property dashboard
│-- app.py  # Main Flask application
│-- requirements.txt  # Required Python packages
│-- .env  # Environment variables
```

## Contributing
Feel free to submit issues and pull requests. Contributions are welcome!

## License
This project is licensed under the MIT License.

---
### Author
**Yogesh Chauhan**

For any queries, contact: `yc993205@gmail.com`

