import bcrypt
from database import SessionLocal
import models

def crear_usuario_admin():
    db = SessionLocal()
    try:
        # Define los datos del administrador de prueba
        username_ingresado = "admin"
        password_ingresado = "admin123"
        rol_asignado = "super_admin"  # Puede ser "super_admin" o "admin"

        # Verificar si el usuario ya existe
        usuario_existente = db.query(models.UsuarioAdmin).filter(
            models.UsuarioAdmin.username == username_ingresado
        ).first()

        if usuario_existente:
            print(f"⚠️ El usuario '{username_ingresado}' ya existe en la base de datos.")
            return

        # Cifrar la contraseña con bcrypt
        password_bytes = password_ingresado.encode('utf-8')
        hashed_bytes = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
        password_hash_str = hashed_bytes.decode('utf-8')

        # Crear la instancia del modelo
        nuevo_admin = models.UsuarioAdmin(
            username=username_ingresado,
            password_hash=password_hash_str,
            rol=rol_asignado
        )

        db.add(nuevo_admin)
        db.commit()
        print(f"✅ ¡Administrador creado con éxito!")
        print(f"   - Usuario: {username_ingresado}")
        print(f"   - Contraseña: {password_ingresado}")
        print(f"   - Rol: {rol_asignado}")

    except Exception as e:
        db.rollback()
        print(f"❌ Ocurrió un error al crear el administrador: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    crear_usuario_admin()