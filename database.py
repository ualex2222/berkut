import sqlite3
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash

DB_FILE = "berkut.db"

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # 1. Таблиця користувачів
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                failed_attempts INTEGER DEFAULT 0,
                lock_until TEXT
            )
        ''')
        
        # Сносимо стару таблицю типів об'єктів для перезапису структури
        cursor.execute("DROP TABLE IF EXISTS object_types")
        
        # 2. Нова таблиця типів об'єктів
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS object_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                category TEXT NOT NULL,
                nato_code TEXT NOT NULL
            )
        ''')
        
        # 3. Таблиця об'єктів обстановки на карті
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS map_objects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lat REAL NOT NULL,
                lng REAL NOT NULL,
                type_id INTEGER NOT NULL,
                side TEXT NOT NULL,
                manpower INTEGER DEFAULT 0,
                details TEXT,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(type_id) REFERENCES object_types(id)
            )
        ''')

        # 4. Таблиця маршрутів (заголовки)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS routes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                color TEXT NOT NULL,
                created_by TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 5. Таблиця точок маршруту (зв'язок з маршрутом)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS route_points (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                route_id INTEGER NOT NULL,
                lat REAL NOT NULL,
                lng REAL NOT NULL,
                sequence INTEGER NOT NULL,
                FOREIGN KEY(route_id) REFERENCES routes(id) ON DELETE CASCADE
            )
        ''')

        # 6. Таблица логов действий (АУДИТ СИСТЕМЫ)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS action_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            action TEXT NOT NULL,
            object_id INTEGER,

            user TEXT NOT NULL,
            role TEXT NOT NULL,

            type_name TEXT,
            icon TEXT,

            details TEXT,

            lat REAL,
            lng REAL,

            created_at TEXT NOT NULL
        )
        ''')
        
        conn.commit()

        # Дефолтний адмін
        cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
        if cursor.fetchone()[0] == 0:
            admin_pass = generate_password_hash("sirko92")
            cursor.execute(
                "INSERT INTO users (username, name, password_hash, role) VALUES (?, ?, ?, ?)",
                ("admin", "Командир / Адмін", admin_pass, "admin")
            )
            
        # Максимально деталізований тактичний арсенал
        cursor.execute("SELECT COUNT(*) FROM object_types")
        if cursor.fetchone()[0] == 0:
            tactical_arsenal = [
    # === ЖИВА СИЛА, ПОЗИЦІЇ ТА ФОРТИФІКАЦІЯ ===
    ("Піхотна група / Вогнева точка (2-5 чол)", "Жива сила та Фортифікація", "infantry1.png"),
    ("Штурмова група / Відділення (6-12 чол)", "Жива сила та Фортифікація", "infantry.png"),
    ("Взводний опорний пункт (ВОП)", "Жива сила та Фортифікація", "vop.png"),
    ("Ротний опорний пункт (РОП)", "Жива сила та Фортифікація", "comrot.png"),
    ("Спостережний пункт (СП / ОП)", "Жива сила та Фортифікація", "ksp.png"),
    ("Командно-спостережний пункт (КСП)", "Жива сила та Фортифікація", "combat.png"),
    ("Командний пункт / Штаб (батальйону / бригади)", "Жива сила та Фортифікація", "combrig.png"),
    ("Снайперська позиція / Розрахунок", "Жива сила та Фортифікація", "sniper.png"),
    ("Бліндаж / Перекрита щілина (особовий склад)", "Жива сила та Фортифікація", "base.png"),
    ("Район зосередження резервів", "Жива сила та Фортифікація", "rezerv.png"),

    # === ЛОГІСТИКА ТА СКЛАДИ ===
    ("Склад артилерійських боєприпасів (БК / РАО)", "Логістика та Склади", "skladart.png"),
    ("Склад тактичного рівня (патрони, ВОГ, гранати)", "Логістика та Склади", "skladpatron.png"),
    ("Склад паливно-мастильних матеріалів (ПММ)", "Логістика та Склади", "kanistra.png"),
    ("Пункт боєпостачання / Перегрузки БК", "Логістика та Склади", "punktboepost.png"),
    ("Медичний пункт / Точка збору поранених (Медевак)", "Жива сила та Фортифікація", "medpunkt.png"),
    ("Пункт тимчасової дислокації (ПТД / Розміщення о/с)", "Логістика та Склади", "punkttumch.png"),
    ("Пункт ремонту та відновлення техніки (ПТОР)", "Логістика та Склади", "sto.png"),
    ("Автозаправник / Вантажівка підвезення ПММ", "Логістика та Склади", "oiltanker.png"),

    # === ІНЖЕНЕРНІ ЗАГОРОДЖЕННЯ ===
    ("Протитанкове мінне поле", "Інженерні загородження", "tm62.png"),
    ("Протипіхотне мінне поле / Розтяжки", "Інженерні загородження", "grenade.png"),
    ("Вузол дистанційного мінування", "Інженерні загородження", "ppo1.png"),
    ("Фортифікаційні загородження (Зуби дракона)", "Інженерні загородження", "dragonteeth.png"),
    ("Протипіхотне мінне поле", "Інженерні загородження", "pom.png"),
    ("Інженерна техніка розгородження (ІМР / БАТ)", "Інженерні загородження", "bat2.png"),
    ("Колючий дріт", "Інженерні загородження", "ograda.png"),

    # === АВІАЦІЯ ТА БПЛА ===
    ("Квадрокоптер розвідувальний (Mavic)", "Авіація та БПЛА", "mavic.png"),
    ("Квадрокоптер (Mavic 3T)", "Авіація та БПЛА", "mavic3t.png"),
    ("БПЛА тактичної розвідки", "Авіація та БПЛА", "uav.png"),
    ("FPV-дрон камікадзе", "Авіація та БПЛА", "fpv.png"),
    ("Баражуючий боєприпас (Lancet)", "Авіація та БПЛА", "lancet.png"),
    ("Важкий ударний БПЛА", "Авіація та БПЛА", "heavydrone.png"),
    ("Фронтовий винищувач", "Авіація та БПЛА", "air-force.png"),
    ("Винищувач", "Авіація та БПЛА", "jet.png"),
    ("Штурмовик", "Авіація та БПЛА", "air-force2.png"),
    ("Транспортна авіація", "Авіація та БПЛА", "air-force3.png"),
    ("Ударний гелікоптер", "Авіація та БПЛА", "apache.png"),
    ("Багатоцільовий гелікоптер", "Авіація та БПЛА", "helicopter.png"),

    # === АРТИЛЕРІЯ, РСЗВ ТА РАКЕТНІ КОМПЛЕКСИ ===
    ("Мінометний розрахунок (82-мм / 120-мм)", "Артилерія", "mortar.png"),
    ("Причіпна артилерія (гаубиці / гармати)", "Артилерія", "cannon.png"),
    ("САУ легка / середнього калібру (122-мм / 152-мм)", "Артилерія", "sau.png"),
    ("САУ важка / західного зразка (155-мм)", "Артилерія", "sau3.png"),
    ("САУ", "Артилерія", "sau2.png"),
    ("РСЗВ (Град / Ураган / Vampire)", "Артилерія", "missiles.png"),
    ("Ракетна система оперативного рівня (Іскандер / ATACMS)", "Артилерія", "missile.png"),
    ("ПТРК (Протитанковий комплекс)", "Артилерія", "ptrk.png"),

    # === БРОНЕТЕХНІКА ТА ТРАНСПОРТ ===
    ("Основний бойовий танк", "Бронетехніка та Транспорт", "tank.png"),
    ("Бойова машина піхоти (БМП)", "Бронетехніка та Транспорт", "bmp.png"),
    ("Бронетранспортер (БТР-80)", "Бронетехніка та Транспорт", "btr.png"),
    ("МТ-ЛБ", "Бронетехніка та Транспорт", "mtlb.png"),
    ("Бронеавтомобіль / Jeep", "Бронетехніка та Транспорт", "jeep.png"),
    ("Вантажівка логістики", "Бронетехніка та Транспорт", "truck.png"),
    ("Легка бронемашина (ПТ-кейс)", "Бронетехніка та Транспорт", "btr2.png"),

    # === ПРОТИПОВІТРЯНА ОБОРОНА (ППО) ===
    ("ПЗРК (Ігла / Stinger)", "Протиповітряна оборона", "javelin.png"),
    ("Мобільна вогнева група (пікап)", "Протиповітряна оборона", "mobgroup.png"),
    ("Зенітна установка (ЗУ-23-4 / ЗУ-23-2)", "Протиповітряна оборона", "zu23-4.png"),
    ("ЗСУ / ЗПРК ближньої дії (Шилка / Gepard / Панцир)", "Протиповітряна оборона", "ppo2.png"),
    ("ЗРК середньої дальності (Бук / IRIS-T / NASAMS)", "Протиповітряна оборона", "buk.png"),
    ("ЗРК дальньої дії / ПРО (С-300 / С-400 / Patriot)", "Протиповітряна оборона", "c400.png"),

    # === РЕБ ТА РАДАРИ ===
    ("Позиція окопного РЕБ", "РЕБ та Радари", "transmitter.png"),
    ("РЛС (Антенний комплекс)", "РЕБ та Радари", "rls2.png"),
    ("РЛС на вантажівці", "РЕБ та Радари", "rls.png"),
    ("Зелена антена / РЛС моніторингу", "РЕБ та Радари", "radar2.png"),
    ("Термінал супутникового зв'язку", "РЕБ та Радари", "satellite.png"),
    ("Радіостанція (Harris)", "РЕБ та Радари", "harris.png"),

    # === МОРСЬКІ БЕЗПІЛОТНИКИ ТА ФЛОТ ===
    ("Нафтова вишка", "Морські безпілотники та Флот", "oilstation.png"),
    ("Ударний безпілотний катер", "Морські безпілотники та Флот", "boat.png"),
    ("Військовий корабель (Катер)", "Морські безпілотники та Флот", "ship1.png"),
    ("Ракетний крейсер", "Морські безпілотники та Флот", "ship4.png"),
    ("Лінкор", "Морські безпілотники та Флот", "linkor.png"),
    ("Авіаносний корабель", "Морські безпілотники та Флот", "ship2.png"),
    ("Корабель з вертолітним майданчиком", "Морські безпілотники та Флот", "ship3.png"),
    ("Підводний човен", "Морські безпілотники та Флот", "submarine.png"),

    # === ELSE ===
    ("Знак хімічної загрози", "Інше", "chemicalwarning.png")
]
            cursor.executemany("INSERT INTO object_types (name, category, nato_code) VALUES (?, ?, ?)", tactical_arsenal)
            conn.commit()
            
        conn.commit()

if __name__ == "__main__":
    print("[+] Повне перезаписування довідника військової номенклатури НАТО...")
    init_db()
    print("[+] База даних berkut.db успішно оновлена. Нові категорії додано.")