from flask import Blueprint, request, redirect, url_for, render_template, session, flash
from datetime import datetime
from werkzeug.security import generate_password_hash
from database import get_db_connection

admin_bp = Blueprint('admin_bp', __name__)

@admin_bp.route('/admin', methods=['GET', 'POST'])
def admin_panel():
    if 'user' not in session or session.get('role') != 'admin':
        flash("Доступ обмежено.", "danger")
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        action = request.form.get('action')
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            if action == 'create_user':
                username = request.form.get('username').strip().lower()
                name = request.form.get('name').strip()
                password = request.form.get('password')
                role = request.form.get('role')
                
                try:
                    p_hash = generate_password_hash(password)
                    cursor.execute("INSERT INTO users (username, name, password_hash, role) VALUES (?, ?, ?, ?)", (username, name, p_hash, role))
                    conn.commit()
                    flash(f"Користувача {name} успішно додано.", "success")
                except:
                    flash("Логін вже зайнятий!", "danger")
                        
            elif action == 'update_name':
                user_id = request.form.get('user_id')
                new_name = request.form.get('new_name').strip()
                cursor.execute("UPDATE users SET name = ? WHERE id = ?", (new_name, user_id))
                conn.commit()
                
            elif action == 'change_password':
                user_id = request.form.get('user_id')
                new_password = request.form.get('new_password')
                p_hash = generate_password_hash(new_password)
                cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (p_hash, user_id))
                conn.commit()
                flash("Пароль оновлено.", "success")
                
            elif action == 'unlock_user':
                user_id = request.form.get('user_id')
                cursor.execute("UPDATE users SET failed_attempts = 0, lock_until = NULL WHERE id = ?", (user_id,))
                conn.commit()
                
            elif action == 'delete_user':
                user_id = request.form.get('user_id')
                cursor.execute("SELECT username FROM users WHERE id = ?", (user_id,))
                if cursor.fetchone()[0] == session.get('user'):
                    flash("Не можна видалити себе!", "danger")
                else:
                    cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
                    conn.commit()
                    flash("Користувача видалено.", "success")
                    
        return redirect(url_for('admin_bp.admin_panel'))
        
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, name, role, failed_attempts, lock_until FROM users")
        users_list = [dict(row) for row in cursor.fetchall()]
        
    return render_template('admin.html', users=users_list, current_time=datetime.now().isoformat())

@admin_bp.route('/admin/logs')
def admin_logs():
    if 'user' not in session or session.get('role') != 'admin':
        flash("Доступ обмежено.", "danger")
        return redirect(url_for('index'))

    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT 
                l.id,
                l.action,
                l.user,
                l.role,
                l.details,
                l.lat,
                l.lng,
                l.created_at,

                o.id AS object_id,
                t.name AS object_name,
                t.category AS category_name,
                t.nato_code AS icon

            FROM action_logs l
            LEFT JOIN map_objects o ON l.object_id = o.id
            LEFT JOIN object_types t ON o.type_id = t.id

            ORDER BY l.id DESC
            LIMIT 200
        """)

        logs = [dict(row) for row in cursor.fetchall()]

    return render_template("logs.html", logs=logs)