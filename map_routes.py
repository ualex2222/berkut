from flask import Blueprint, request, jsonify, session, current_app
from datetime import datetime

import requests
import srtm
from database import get_db_connection

map_bp = Blueprint('map_bp', __name__)

def write_log(action, object_id=None, details=None, lat=None, lng=None, object_type_id=None):
    try:
        icon = None
        type_name = None

        # 🔥 если передан type_id — тянем из базы
        if object_type_id:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT name, nato_code
                    FROM object_types
                    WHERE id = ?
                """, (object_type_id,))
                row = cursor.fetchone()

                if row:
                    type_name = row["name"]
                    icon = row["nato_code"]

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO action_logs (
                    action, object_id, user, role,
                    type_name, icon,
                    details, lat, lng, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                action,
                object_id,
                session.get('name'),
                session.get('role'),
                type_name,
                icon,
                details,
                lat,
                lng,
                datetime.now().strftime("%d.%m.%Y %H:%M:%S")
            ))
            conn.commit()

    except Exception as e:
        current_app.logger.error(f"LOG ERROR: {e}")

@map_bp.route('/api/map-data', methods=['GET'])
def get_map_data():
    if 'user' not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Отримуємо довідник типів для випадаючих списків
        cursor.execute("SELECT * FROM object_types ORDER BY name")
        types = [dict(row) for row in cursor.fetchall()]
        
        # ВИПРАВЛЕНО: Змінено з 'objects' на 'map_objects' + вирівняно відступи
        cursor.execute("""
            SELECT o.*, t.name as type_name, t.category as category_name, t.nato_code 
            FROM map_objects o 
            JOIN object_types t ON o.type_id = t.id
        """)
        objects = [dict(row) for row in cursor.fetchall()]
        
    return jsonify({"types": types, "objects": objects})


@map_bp.route('/api/objects', methods=['POST'])
def create_map_object():
    if 'user' not in session or session.get('role') not in ['admin', 'operator']:
        return jsonify({"error": "Немає прав для внесення змін"}), 403
        
    data = request.json
    lat = data.get('lat')
    lng = data.get('lng')
    type_id = data.get('type_id')
    side = data.get('side')
    manpower = data.get('manpower', 0)
    details = data.get('details', '')
    
    created_by = session.get('name')
    created_at = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    
    if not lat or not lng or not type_id or not side:
        return jsonify({"error": "Відсутні обов'язкові параметри"}), 400
        
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO map_objects (lat, lng, type_id, side, manpower, details, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (lat, lng, type_id, side, manpower, details, created_by, created_at))
        conn.commit()
        new_id = cursor.lastrowid
        
        # ОПТИМІЗАЦІЯ: Тягнемо ПОВНІ дані типу (включаючи nato_code та category), 
        # щоб фронтенд міг відразу відрендерити правильну тактичну іконку
        cursor.execute("SELECT name, category, nato_code FROM object_types WHERE id = ?", (type_id,))
        type_info = cursor.fetchone()

    broadcast_data = {
        "action": "create",
        "id": new_id,
        "lat": lat,
        "lng": lng,
        "type_id": type_id,
        "type_name": type_info['name'] if type_info else "Невідомо",
        "category_name": type_info['category'] if type_info else "Інше",
        "nato_code": type_info['nato_code'] if type_info else None,
        "side": side,
        "manpower": manpower,
        "details": details,
        "created_by": created_by,
        "created_at": created_at
    }
    
    # Відправка в реалтаймі всім клієнтам
    current_app.socketio.emit('map_action', broadcast_data, to='/')
    
    write_log(
        action="CREATE",
        object_id=new_id,
        object_type_id=type_id,
        details=side,
        lat=lat,
        lng=lng
    )
    
    return jsonify({"status": "success", "object": broadcast_data}), 201


@map_bp.route('/api/objects/<int:obj_id>', methods=['DELETE'])
def delete_map_object(obj_id):
    if 'user' not in session or session.get('role') not in ['admin', 'operator']:
        return jsonify({"error": "Немає прав для видалення"}), 403
        
    user_role = session.get('role')
    user_name = session.get('name')
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT created_by FROM map_objects WHERE id = ?", (obj_id,))
        obj = cursor.fetchone()
        
        if not obj:
            return jsonify({"error": "Об'єкт не знайдено"}), 404
            
        if user_role != 'admin' and obj['created_by'] != user_name:
            return jsonify({"error": "Ви можете видаляти лише створені вами об'єкти"}), 403
            
        cursor.execute("DELETE FROM map_objects WHERE id = ?", (obj_id,))
        conn.commit()
        
    broadcast_data = {
        "action": "delete",
        "id": obj_id
    }
    
    current_app.socketio.emit('map_action', broadcast_data, to='/')
    
    write_log(
        action="DELETE",
        object_id=obj_id,
        details="Object removed"
    )
    
    return jsonify({"status": "success"}), 200


@map_bp.route('/api/objects/<int:obj_id>/move', methods=['POST'])
def move_map_object(obj_id):
    """Оновлює позицію або параметри точки на льоту."""
    if 'user' not in session or session.get('role') not in ['admin', 'operator']:
        return jsonify({"error": "Немає прав для внесення змін"}), 403
        
    data = request.json
    lat = data.get('lat')
    lng = data.get('lng')
    manpower = data.get('manpower') 
    details = data.get('details')   
    
    if not lat or not lng:
        return jsonify({"error": "Координати обов'язкові"}), 400
        
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Оновлюємо змінні в базі
        if manpower is not None or details is not None:
            cursor.execute('''
                UPDATE map_objects 
                SET lat = ?, lng = ?, manpower = COALESCE(?, manpower), details = COALESCE(?, details)
                WHERE id = ?
            ''', (lat, lng, manpower, details, obj_id))
        else:
            cursor.execute("UPDATE map_objects SET lat = ?, lng = ? WHERE id = ?", (lat, lng, obj_id))
            
        conn.commit()
        
        # ОПТИМІЗАЦІЯ: Збираємо повний зліпок об'єкта після оновлення для безшовної синхронізації
        cursor.execute("""
            SELECT o.*, t.name as type_name, t.category as category_name, t.nato_code 
            FROM map_objects o 
            JOIN object_types t ON o.type_id = t.id
            WHERE o.id = ?
        """, (obj_id,))
        updated_row = cursor.fetchone()

    if not updated_row:
        return jsonify({"error": "Об'єкт зник під час оновлення"}), 404

    # Конвертуємо результат у словник та додаємо керуючий екшен для фронтенду
    broadcast_data = dict(updated_row)
    broadcast_data["action"] = "update"
    
    # Транслюємо повний пакет змін через сокети
    current_app.socketio.emit('map_action', broadcast_data, to='/')
    
    write_log(
        action="MOVE",
        object_id=obj_id,
        details="Position updated",
        lat=lat,
        lng=lng
    )
    
    return jsonify({"status": "success"}), 200

# ВЫСОТА

elevation_data = srtm.get_data(local_cache_dir='static/h')

@map_bp.route('/api/elevation', methods=['GET'])
def get_elevation():
    try:
        lat = float(request.args.get('lat'))
        lng = float(request.args.get('lng'))
        
        # Отримуємо висоту з локальної бази
        altitude = elevation_data.get_elevation(lat, lng)
        
        # Якщо в точці немає даних, srtm повертає None
        # Повертаємо 0, якщо даних немає
        return jsonify({
            "lat": lat,
            "lng": lng,
            "altitude": int(altitude) if altitude is not None else 0,
            "source": "local_srtm_db"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@map_bp.route('/api/profile', methods=['POST'])
def get_profile():
    coords = request.json.get('points') # Очікуємо список [{lat:..., lng:...}, ...]
    profile = []
    for p in coords:
        alt = elevation_data.get_elevation(p['lat'], p['lng'])
        profile.append(int(alt) if alt is not None else 0)
    return jsonify({"profile": profile})

# МАРШРУТЫ

@map_bp.route('/api/routes', methods=['GET'])
def get_routes():
    """Отримання всіх маршрутів з їхніми точками."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Отримуємо всі маршрути
        cursor.execute("SELECT * FROM routes")
        routes = [dict(row) for row in cursor.fetchall()]
        
        # Для кожного маршруту підтягуємо його точки
        for route in routes:
            cursor.execute("SELECT lat, lng, sequence FROM route_points WHERE route_id = ? ORDER BY sequence", (route['id'],))
            route['points'] = [dict(row) for row in cursor.fetchall()]
            
    return jsonify(routes)

@map_bp.route('/api/routes', methods=['POST'])
def create_route():
    """Створення маршруту та його точок."""
    if 'user' not in session or session.get('role') not in ['admin', 'operator']:
        return jsonify({"error": "Немає прав"}), 403
        
    data = request.json
    name = data.get('name')
    color = data.get('color', '#FF0000')
    points = data.get('points', []) # Очікуємо масив [{lat, lng}, ...]
    
    if not name or not points:
        return jsonify({"error": "Назва та точки є обов'язковими"}), 400
        
    created_by = session.get('name')
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # 1. Створюємо запис маршруту
        cursor.execute(
            "INSERT INTO routes (name, color, created_by) VALUES (?, ?, ?)",
            (name, color, created_by)
        )
        route_id = cursor.lastrowid
        
        # 2. Додаємо точки
        for idx, p in enumerate(points):
            cursor.execute(
                "INSERT INTO route_points (route_id, lat, lng, sequence) VALUES (?, ?, ?, ?)",
                (route_id, p['lat'], p['lng'], idx)
            )
        conn.commit()
        
    return jsonify({"status": "success", "route_id": route_id}), 201

@map_bp.route('/api/routes/<int:route_id>', methods=['DELETE'])
def delete_route(route_id):
    """Видалення маршруту з перевіркою прав доступу та авторства."""
    if 'user' not in session or session.get('role') not in ['admin', 'operator']:
        return jsonify({"error": "Немає прав"}), 403
        
    user_role = session.get('role')
    user_name = session.get('name')
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # 1. Отримуємо інформацію про маршрут, щоб перевірити автора
        cursor.execute("SELECT created_by FROM routes WHERE id = ?", (route_id,))
        route = cursor.fetchone()
        
        if not route:
            return jsonify({"error": "Маршрут не знайдено"}), 404
            
        # 2. Перевірка: адмін може видаляти все, оператор — тільки своє
        if user_role != 'admin' and route['created_by'] != user_name:
            return jsonify({"error": "Ви можете видаляти лише створені вами маршрути"}), 403
            
        # 3. Видалення
        cursor.execute("DELETE FROM routes WHERE id = ?", (route_id,))
        conn.commit()
        
    # (Опціонально) Додайте сюди socketio.emit, якщо потрібно оновлювати карту в реальному часі
    # current_app.socketio.emit('route_action', {"action": "delete", "id": route_id}, to='/')
        
    return jsonify({"status": "success"}), 200

@map_bp.route('/api/frontline', methods=['GET'])
def get_frontline():

    try:
        response = requests.get(
            "https://deepstatemap.live/api/history/last",
            timeout=30
        )

        response.raise_for_status()

        data = response.json()

        return jsonify({
            "datetime": data.get("datetime"),
            "id": data.get("id"),
            "map": data.get("map")
        })

    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500