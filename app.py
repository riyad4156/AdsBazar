from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, g
import sqlite3
import os
import re
import secrets
from database import init_db, get_db
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.DEBUG, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.secret_key = secrets.token_hex(16)  # Generate a random secret key
app.config['SESSION_TYPE'] = 'filesystem'
app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1 hour

# Initialize database
init_db(app)

# Routes
@app.route('/')
def welcome():
    return render_template('welcome.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            # Get form data
            name = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip()
            password = request.form.get('password', '')
            
            # Validate form data
            if not name or not email or not password:
                flash('All fields are required', 'error')
                return render_template('register.html')
            
            # Validate email format
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, email):
                flash('Invalid email format', 'error')
                return render_template('register.html')
            
            # Connect to database
            db = get_db()
            cursor = db.cursor()
            
            # Check if email already exists
            cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
            if cursor.fetchone():
                flash('Email already registered', 'error')
                return render_template('register.html')
            
            # Insert new user
            cursor.execute(
                "INSERT INTO users (name, email, password, balance) VALUES (?, ?, ?, ?)",
                (name, email, password, 0)
            )
            db.commit()
            
            flash('Registration successful! Please login.', 'success')
            logger.info(f"New user registered: {email}")
            return redirect(url_for('login'))
            
        except Exception as e:
            logger.error(f"Error during registration: {e}")
            flash('An error occurred during registration. Please try again.', 'error')
            return render_template('register.html')
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            # Get form data
            email = request.form.get('email', '').strip()
            password = request.form.get('password', '')
            
            # Validate form data
            if not email or not password:
                flash('Email and password are required', 'error')
                return render_template('login.html')
            
            # Connect to database
            db = get_db()
            cursor = db.cursor()
            
            # Check if user exists and password matches
            cursor.execute(
                "SELECT * FROM users WHERE email = ? AND password = ?",
                (email, password)
            )
            user = cursor.fetchone()
            
            if user:
                # Store user data in session
                session.clear()
                session['user_id'] = user['id']
                session['user_name'] = user['name']
                session['user_email'] = user['email']
                session['user_balance'] = user['balance']
                
                flash('Login successful!', 'success')
                logger.info(f"User logged in: {email}")
                return redirect(url_for('dashboard'))
            else:
                flash('Invalid email or password', 'error')
                return render_template('login.html')
                
        except Exception as e:
            logger.error(f"Error during login: {e}")
            flash('An error occurred during login. Please try again.', 'error')
            return render_template('login.html')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('welcome'))

@app.route('/dashboard')
def dashboard():
    # Check if user is logged in
    if 'user_id' not in session:
        flash('Please login to access the dashboard', 'error')
        return redirect(url_for('login'))
    
    try:
        # Connect to database
        db = get_db()
        cursor = db.cursor()
        
        # Get user's current balance
        cursor.execute("SELECT balance FROM users WHERE id = ?", (session['user_id'],))
        user_data = cursor.fetchone()
        
        if not user_data:
            flash('User data not found', 'error')
            session.clear()
            return redirect(url_for('login'))
            
        balance = user_data['balance']
        
        # Get available ads
        cursor.execute("SELECT * FROM ads")
        ads = cursor.fetchall()
        
        return render_template('dashboard.html', balance=balance, ads=ads)
        
    except Exception as e:
        logger.error(f"Error accessing dashboard: {e}")
        flash('An error occurred. Please try again.', 'error')
        return redirect(url_for('welcome'))

@app.route('/reward', methods=['POST'])
def reward():
    # Check if user is logged in
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})
    
    try:
        # Get request data
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'})
            
        ad_id = data.get('ad_id')
        watched_fully = data.get('watched_fully')
        
        if not ad_id:
            return jsonify({'success': False, 'message': 'Ad ID is required'})
        
        # Connect to database
        db = get_db()
        cursor = db.cursor()
        
        if watched_fully:
            # Update user balance (changed from 3 to 2 taka)
            cursor.execute(
                "UPDATE users SET balance = balance + 2 WHERE id = ?",
                (session['user_id'],)
            )
            
            # Record the ad view
            cursor.execute(
                "INSERT INTO ad_views (user_id, ad_id, rewarded) VALUES (?, ?, ?)",
                (session['user_id'], ad_id, True)
            )
            
            db.commit()
            
            # Update session balance
            session['user_balance'] = session.get('user_balance', 0) + 2
            
            logger.info(f"User {session['user_id']} earned reward for ad {ad_id}")
            return jsonify({'success': True, 'new_balance': session['user_balance']})
        else:
            # Record that the ad was not fully watched
            cursor.execute(
                "INSERT INTO ad_views (user_id, ad_id, rewarded) VALUES (?, ?, ?)",
                (session['user_id'], ad_id, False)
            )
            db.commit()
            
            logger.info(f"User {session['user_id']} did not complete ad {ad_id}")
            return jsonify({'success': False, 'message': 'Ad not watched fully'})
            
    except Exception as e:
        logger.error(f"Error processing reward: {e}")
        return jsonify({'success': False, 'message': f'An error occurred: {str(e)}'})

@app.route('/withdraw', methods=['GET', 'POST'])
def withdraw():
    # Check if user is logged in
    if 'user_id' not in session:
        flash('Please login to access the withdrawal page', 'error')
        return redirect(url_for('login'))
    
    try:
        # Connect to database
        db = get_db()
        cursor = db.cursor()
        
        # Get user's current balance
        cursor.execute("SELECT balance FROM users WHERE id = ?", (session['user_id'],))
        user_data = cursor.fetchone()
        
        if not user_data:
            flash('User data not found', 'error')
            session.clear()
            return redirect(url_for('login'))
            
        balance = user_data['balance']
        
        # Get withdrawal history
        cursor.execute(
            "SELECT * FROM withdrawals WHERE user_id = ? ORDER BY request_date DESC",
            (session['user_id'],)
        )
        withdrawal_history = cursor.fetchall()
        
        if request.method == 'POST':
            # Get form data
            amount = float(request.form.get('amount', 0))
            payment_method = request.form.get('payment_method', '').strip()
            payment_details = request.form.get('payment_details', '').strip()
            
            # Validate form data
            if not amount or not payment_method or not payment_details:
                flash('All fields are required', 'error')
                return render_template('withdraw.html', balance=balance, withdrawal_history=withdrawal_history)
            
            # Validate amount
            if amount < 300:
                flash('Minimum withdrawal amount is BDT 300', 'error')
                return render_template('withdraw.html', balance=balance, withdrawal_history=withdrawal_history)
                
            if amount > 1000:
                flash('Maximum withdrawal amount is BDT 1000', 'error')
                return render_template('withdraw.html', balance=balance, withdrawal_history=withdrawal_history)
                
            if amount > balance:
                flash('Insufficient balance', 'error')
                return render_template('withdraw.html', balance=balance, withdrawal_history=withdrawal_history)
            
            # Check if there's a pending withdrawal
            cursor.execute(
                "SELECT COUNT(*) as count FROM withdrawals WHERE user_id = ? AND status = 'pending'",
                (session['user_id'],)
            )
            pending_count = cursor.fetchone()['count']
            
            if pending_count > 0:
                flash('You already have a pending withdrawal request', 'error')
                return render_template('withdraw.html', balance=balance, withdrawal_history=withdrawal_history)
            
            # Create withdrawal request
            cursor.execute(
                "INSERT INTO withdrawals (user_id, amount, payment_method, payment_details, status) VALUES (?, ?, ?, ?, ?)",
                (session['user_id'], amount, payment_method, payment_details, 'pending')
            )
            
            # Deduct amount from user balance
            cursor.execute(
                "UPDATE users SET balance = balance - ? WHERE id = ?",
                (amount, session['user_id'])
            )
            
            db.commit()
            
            # Update session balance
            session['user_balance'] = balance - amount
            
            flash('Withdrawal request submitted successfully', 'success')
            logger.info(f"User {session['user_id']} requested withdrawal of BDT {amount}")
            
            # Refresh withdrawal history
            cursor.execute(
                "SELECT * FROM withdrawals WHERE user_id = ? ORDER BY request_date DESC",
                (session['user_id'],)
            )
            withdrawal_history = cursor.fetchall()
            
            return render_template('withdraw.html', balance=session['user_balance'], withdrawal_history=withdrawal_history)
        
        return render_template('withdraw.html', balance=balance, withdrawal_history=withdrawal_history)
        
    except Exception as e:
        logger.error(f"Error processing withdrawal: {e}")
        flash('An error occurred. Please try again.', 'error')
        return redirect(url_for('dashboard'))

@app.route('/admin/withdrawals')
def admin_withdrawals():
    # Check if user is logged in and is admin (for simplicity, let's assume user_id 1 is admin)
    if 'user_id' not in session or session['user_id'] != 1:
        flash('Unauthorized access', 'error')
        return redirect(url_for('login'))
    
    try:
        # Connect to database
        db = get_db()
        cursor = db.cursor()
        
        # Get all pending withdrawals
        cursor.execute("""
            SELECT w.*, u.name, u.email 
            FROM withdrawals w 
            JOIN users u ON w.user_id = u.id 
            ORDER BY w.request_date DESC
        """)
        withdrawals = cursor.fetchall()
        
        return render_template('admin_withdrawals.html', withdrawals=withdrawals)
        
    except Exception as e:
        logger.error(f"Error accessing admin withdrawals: {e}")
        flash('An error occurred. Please try again.', 'error')
        return redirect(url_for('dashboard'))

@app.route('/admin/process_withdrawal', methods=['POST'])
def process_withdrawal():
    # Check if user is logged in and is admin
    if 'user_id' not in session or session['user_id'] != 1:
        return jsonify({'success': False, 'message': 'Unauthorized access'})
    
    try:
        # Get request data
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'})
            
        withdrawal_id = data.get('withdrawal_id')
        action = data.get('action')  # 'approve' or 'reject'
        admin_note = data.get('admin_note', '')
        
        if not withdrawal_id or not action:
            return jsonify({'success': False, 'message': 'Withdrawal ID and action are required'})
        
        # Connect to database
        db = get_db()
        cursor = db.cursor()
        
        # Get withdrawal details
        cursor.execute("SELECT * FROM withdrawals WHERE id = ?", (withdrawal_id,))
        withdrawal = cursor.fetchone()
        
        if not withdrawal:
            return jsonify({'success': False, 'message': 'Withdrawal not found'})
        
        if withdrawal['status'] != 'pending':
            return jsonify({'success': False, 'message': 'Withdrawal has already been processed'})
        
        if action == 'approve':
            # Update withdrawal status
            cursor.execute(
                "UPDATE withdrawals SET status = 'completed', processed_date = ?, admin_note = ? WHERE id = ?",
                (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), admin_note, withdrawal_id)
            )
            
            status_message = 'Withdrawal approved successfully'
            new_status = 'completed'
            
        elif action == 'reject':
            # Update withdrawal status
            cursor.execute(
                "UPDATE withdrawals SET status = 'rejected', processed_date = ?, admin_note = ? WHERE id = ?",
                (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), admin_note, withdrawal_id)
            )
            
            # Refund amount to user balance
            cursor.execute(
                "UPDATE users SET balance = balance + ? WHERE id = ?",
                (withdrawal['amount'], withdrawal['user_id'])
            )
            
            status_message = 'Withdrawal rejected and amount refunded'
            new_status = 'rejected'
            
        else:
            return jsonify({'success': False, 'message': 'Invalid action'})
        
        db.commit()
        
        logger.info(f"Admin {session['user_id']} {action}d withdrawal {withdrawal_id}")
        return jsonify({
            'success': True, 
            'message': status_message,
            'new_status': new_status,
            'processed_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
            
    except Exception as e:
        logger.error(f"Error processing withdrawal action: {e}")
        return jsonify({'success': False, 'message': f'An error occurred: {str(e)}'})

@app.route('/debug')
def debug():
    """Debug route to check database connection and tables"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Check if users table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        users_table = cursor.fetchone()
        
        # Check if ads table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ads'")
        ads_table = cursor.fetchone()
        
        # Check if withdrawals table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='withdrawals'")
        withdrawals_table = cursor.fetchone()
        
        # Get user count
        user_count = 0
        if users_table:
            cursor.execute("SELECT COUNT(*) as count FROM users")
            user_count = cursor.fetchone()['count']
        
        # Get ad count
        ad_count = 0
        if ads_table:
            cursor.execute("SELECT COUNT(*) as count FROM ads")
            ad_count = cursor.fetchone()['count']
            
        # Get withdrawal count
        withdrawal_count = 0
        if withdrawals_table:
            cursor.execute("SELECT COUNT(*) as count FROM withdrawals")
            withdrawal_count = cursor.fetchone()['count']
        
        return f"""
        <h1>Debug Information</h1>
        <p>Database connection: Success</p>
        <p>Users table exists: {bool(users_table)}</p>
        <p>Ads table exists: {bool(ads_table)}</p>
        <p>Withdrawals table exists: {bool(withdrawals_table)}</p>
        <p>User count: {user_count}</p>
        <p>Ad count: {ad_count}</p>
        <p>Withdrawal count: {withdrawal_count}</p>
        <p><a href="/">Back to home</a></p>
        """
    except Exception as e:
        return f"""
        <h1>Debug Error</h1>
        <p>Error: {str(e)}</p>
        <p><a href="/">Back to home</a></p>
        """

if __name__ == '__main__':
    app.run(debug=True)
