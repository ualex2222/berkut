from flask import Flask, jsonify, render_template, request, redirect, url_for, session, flash
from flask_socketio import SocketIO
from datetime import datetime, timedelta
from werkzeug.security import check_password_hash
import database
from database import get_db_connection
import srtm

app = Flask(__name__)
app.config['SECRET_KEY'] = '92-sirko-berkut-crypto-secure-key'
socketio = SocketIO(app, cors_allowed_origins="*")

# Инициализируем базу данных (создаем таблицы при первом пуске)
database.init_db()

app.socketio = socketio

# Регистрируем наши новые разделенные файлы-модули
from map_routes import map_bp
from admin_routes import admin_bp

app.register_blueprint(map_bp)
app.register_blueprint(admin_bp)


# Глобальные маршруты авторизации
@app.route('/')
def index():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('index.html', user=session.get('name'), role=session.get('role'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username').strip().lower()
        password = request.form.get('password')
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
            user = cursor.fetchone()
            
            if not user:
                flash("Невірний логін або пароль.", "danger")
                return render_template('login.html')
            
            current_time = datetime.now()
            if user['lock_until'] and current_time < datetime.fromisoformat(user['lock_until']):
                flash("Акаунт тимчасово заблоковано через брутфорс.", "danger")
                return render_template('login.html')
            
            if check_password_hash(user['password_hash'], password):
                cursor.execute("UPDATE users SET failed_attempts = 0, lock_until = NULL WHERE id = ?", (user['id'],))
                conn.commit()
                session['user'] = user['username']
                session['name'] = user['name']
                session['role'] = user['role']
                return redirect(url_for('index'))
            else:
                new_attempts = user['failed_attempts'] + 1
                if new_attempts >= 5:
                    lock_str = (datetime.now() + timedelta(minutes=15)).isoformat()
                    cursor.execute("UPDATE users SET failed_attempts = ?, lock_until = ? WHERE id = ?", (new_attempts, lock_str, user['id']))
                    flash("Акаунт заблоковано на 15 хвилин.", "danger")
                else:
                    cursor.execute("UPDATE users SET failed_attempts = ? WHERE id = ?", (new_attempts, user['id']))
                    flash(f"Невірний пароль. Спроб залишилось: {5 - new_attempts}", "warning")
                conn.commit()
                
    return render_template('login.html')



@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=80, debug=True)