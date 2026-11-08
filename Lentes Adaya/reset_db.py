import psycopg
from sqlalchemy import create_engine
from database import Base, SQLALCHEMY_DATABASE_URL
import models
import bcrypt

def inicializar_base_datos():
    print("Verificando si la base de datos 'optica_db' existe...")
    try:
        # Conexión limpia al servidor por defecto de PostgreSQL
        conn = psycopg.connect("postgresql://postgres:1234@localhost/postgres", autocommit=True)
        cursor = conn.cursor()
        
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = 'optica_db'")
        existe = cursor.fetchone()
        
        if not existe:
            cursor.execute("CREATE DATABASE optica_db;")
            print("--> ¡Base de datos 'optica_db' creada exitosamente!")
        else:
            print("--> La base de datos 'optica_db' ya existe.")
            
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Nota al verificar la base de datos: {e}")

    print("Conectando y recreando las tablas...")
    engine = create_engine(SQLALCHEMY_DATABASE_URL)
    
    # ⚠️ Esto borra las tablas anteriores para forzar que se creen con los nuevos campos de models.py
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    print("--> ¡Tablas recreadas exitosamente con la nueva estructura!")

    from sqlalchemy.orm import Session
    db = Session(bind=engine)

    try:
        # Verificar si ya existe un super_admin
        super_existente = db.query(models.UsuarioAdmin).filter(models.UsuarioAdmin.rol == "super_admin").first()
        if not super_existente:
            password_hash = bcrypt.hashpw("admin123".encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            nuevo_super = models.UsuarioAdmin(
                username="superadmin",
                password_hash=password_hash,
                rol="super_admin"
            )
            db.add(nuevo_super)
            db.commit()
            print("--> Super Admin creado por defecto: usuario 'superadmin' / contraseña 'admin123'")
        else:
            print("--> Ya existe un Super Admin en la base de datos.")
    except Exception as e:
        print(f"Error al crear el super admin: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    inicializar_base_datos()