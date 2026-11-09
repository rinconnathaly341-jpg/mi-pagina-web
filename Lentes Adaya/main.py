from fastapi import FastAPI, Depends, HTTPException, status, File, UploadFile, Form, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import func
from pydantic import BaseModel, EmailStr
from typing import List, Optional
from datetime import datetime, date, timedelta
import shutil
import base64
import bcrypt
import os

import models, database
from database import engine, get_db

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Óptica Leb - API de Monturas y Citas")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
app.mount("/templates", StaticFiles(directory=os.path.join(BASE_DIR, "templates")), name="templates")

INDEX_PATH = os.path.join(BASE_DIR, "static", "index.html")

UPLOADS_DIR = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)

# Límite máximo de citas permitidas por día
LIMITE_CITAS_DIARIAS = 15

class AdminLoginSchema(BaseModel):
    username: str
    password: str

class AdminRegisterSchema(BaseModel):
    super_admin_username: str
    super_admin_password: str
    nuevo_username: str
    nuevo_password: str
    rol: Optional[str] = "admin"

# --- ESQUEMAS PARA CLIENTES / USUARIOS ---
class ClienteRegisterSchema(BaseModel):
    nombre_completo: str
    cedula: str
    telefono: str
    correo: str
    password: str

class ClienteLoginSchema(BaseModel.ConfigDict if hasattr(BaseModel, "ConfigDict") else object):
    correo: str
    password: str

class ClienteUpdateSchema(BaseModel):
    nombre_completo: Optional[str] = None
    telefono: Optional[str] = None
    password_actual: Optional[str] = None
    password_nuevo: Optional[str] = None

class CitaCreate(BaseModel):
    nombre_cliente: str
    cedula: str
    telefono: str
    fecha_cita: date
    montura_id: Optional[int] = None
    resumen_solicitud: str
    monto_total: Optional[float] = 0.00
    usuario_id: Optional[int] = None

@app.get("/", response_class=FileResponse)
def inicio():
    return FileResponse(INDEX_PATH)

@app.get("/admin", response_class=FileResponse)
def vista_admin():
    admin_path = os.path.join(BASE_DIR, "templates", "index_admin.html")
    if not os.path.exists(admin_path):
        admin_path = os.path.join(BASE_DIR, "static", "index_admin.html")
    return FileResponse(admin_path)

@app.get("/citas-admin", response_class=FileResponse)
def vista_citas_admin():
    citas_path = os.path.join(BASE_DIR, "templates", "citas_admin.html")
    if not os.path.exists(citas_path):
        citas_path = os.path.join(BASE_DIR, "static", "citas_admin.html")
    return FileResponse(citas_path)

@app.post("/api/login-admin")
def login_admin(credentials: AdminLoginSchema, db: Session = Depends(get_db)):
    admin = db.query(models.UsuarioAdmin).filter(models.UsuarioAdmin.username == credentials.username).first()
    
    if not admin:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales incorrectas")
    
    password_bytes = credentials.password.encode('utf-8')
    hashed_bytes = admin.password_hash.encode('utf-8')
    
    if not bcrypt.checkpw(password_bytes, hashed_bytes):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales incorrectas")

    return {
        "message": "Acceso concedido", 
        "status": "success",
        "rol": getattr(admin, 'rol', 'admin'),
        "username": admin.username
    }


@app.post("/api/admin/registrar-admin")
def registrar_admin(data: AdminRegisterSchema, db: Session = Depends(get_db)):
    """Solo el super_admin puede registrar nuevos administradores."""
    super_admin = db.query(models.UsuarioAdmin).filter(
        models.UsuarioAdmin.username == data.super_admin_username,
        models.UsuarioAdmin.rol == "super_admin"
    ).first()
    
    if not super_admin:
        raise HTTPException(status_code=403, detail="Acceso denegado: Se requiere cuenta de Super Administrador")
    
    if not bcrypt.checkpw(data.super_admin_password.encode('utf-8'), super_admin.password_hash.encode('utf-8')):
        raise HTTPException(status_code=401, detail="Contraseña de Super Administrador incorrecta")
        
    existente = db.query(models.UsuarioAdmin).filter(models.UsuarioAdmin.username == data.nuevo_username).first()
    if existente:
        raise HTTPException(status_code=400, detail="El nombre de usuario ya está en uso")
        
    hashed_password = bcrypt.hashpw(data.nuevo_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    nuevo_admin = models.UsuarioAdmin(
        username=data.nuevo_username,
        password_hash=hashed_password,
        rol=data.rol if data.rol in ["admin", "super_admin"] else "admin"
    )
    
    db.add(nuevo_admin)
    db.commit()
    return {"status": "success", "message": f"Administrador '{data.nuevo_username}' registrado exitosamente"}


# ==========================================
# ENDPOINTS DE CLIENTES / USUARIOS
# ==========================================

@app.post("/api/clientes/registro")
def registrar_cliente(data: ClienteRegisterSchema, db: Session = Depends(get_db)):
    """Registra un nuevo usuario cliente en la óptica."""
    cedula_existe = db.query(models.UsuarioCliente).filter(models.UsuarioCliente.cedula == data.cedula).first()
    if cedula_existe:
        raise HTTPException(status_code=400, detail="Ya existe una cuenta registrada con esta cédula")

    correo_existe = db.query(models.UsuarioCliente).filter(models.UsuarioCliente.correo == data.correo).first()
    if correo_existe:
        raise HTTPException(status_code=400, detail="El correo electrónico ya está en uso")

    hashed_password = bcrypt.hashpw(data.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    nuevo_cliente = models.UsuarioCliente(
        nombre_completo=data.nombre_completo,
        cedula=data.cedula,
        telefono=data.telefono,
        correo=data.correo,
        password_hash=hashed_password
    )

    db.add(nuevo_cliente)
    db.commit()
    db.refresh(nuevo_cliente)

    return {
        "status": "success",
        "message": "Cuenta creada exitosamente",
        "usuario": {
            "id": nuevo_cliente.id,
            "nombre_completo": nuevo_cliente.nombre_completo,
            "cedula": nuevo_cliente.cedula,
            "telefono": nuevo_cliente.telefono,
            "correo": nuevo_cliente.correo
        }
    }


@app.post("/api/clientes/login")
def login_cliente(data: AdminLoginSchema, db: Session = Depends(get_db)):
    """Inicia sesión para un usuario cliente usando correo y contraseña."""
    cliente = db.query(models.UsuarioCliente).filter(models.UsuarioCliente.correo == data.username).first()
    if not cliente:
        cliente = db.query(models.UsuarioCliente).filter(models.UsuarioCliente.cedula == data.username).first()

    if not cliente:
        raise HTTPException(status_code=401, detail="Correo o contraseña incorrectos")

    if not bcrypt.checkpw(data.password.encode('utf-8'), cliente.password_hash.encode('utf-8')):
        raise HTTPException(status_code=401, detail="Correo o contraseña incorrectos")

    return {
        "status": "success",
        "message": "Bienvenido",
        "usuario": {
            "id": cliente.id,
            "nombre_completo": cliente.nombre_completo,
            "cedula": cliente.cedula,
            "telefono": cliente.telefono,
            "correo": cliente.correo
        }
    }


@app.put("/api/clientes/{usuario_id}/actualizar")
def actualizar_cliente(usuario_id: int, data: ClienteUpdateSchema, db: Session = Depends(get_db)):
    """Permite al usuario actualizar sus datos o cambiar su contraseña."""
    cliente = db.query(models.UsuarioCliente).filter(models.UsuarioCliente.id == usuario_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if data.nombre_completo:
        cliente.nombre_completo = data.nombre_completo
    if data.telefono:
        cliente.telefono = data.telefono

    if data.password_nuevo:
        if not data.password_actual:
            raise HTTPException(status_code=400, detail="Debe ingresar su contraseña actual para realizar el cambio")
        
        if not bcrypt.checkpw(data.password_actual.encode('utf-8'), cliente.password_hash.encode('utf-8')):
            raise HTTPException(status_code=401, detail="La contraseña actual es incorrecta")

        cliente.password_hash = bcrypt.hashpw(data.password_nuevo.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    db.commit()
    db.refresh(cliente)

    return {
        "status": "success",
        "message": "Datos actualizados correctamente",
        "usuario": {
            "id": cliente.id,
            "nombre_completo": cliente.nombre_completo,
            "cedula": cliente.cedula,
            "telefono": cliente.telefono,
            "correo": cliente.correo
        }
    }


@app.delete("/api/clientes/{usuario_id}/eliminar")
def eliminar_cuenta_cliente(usuario_id: int, db: Session = Depends(get_db)):
    """Permite al usuario eliminar su propia cuenta de forma permanente."""
    cliente = db.query(models.UsuarioCliente).filter(models.UsuarioCliente.id == usuario_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    db.delete(cliente)
    db.commit()
    return {"status": "success", "message": "Cuenta eliminada exitosamente"}


# ==========================================
# ENDPOINTS DE MONTURAS (CATÁLOGO)
# ==========================================

@app.get("/api/zapatos/random")
def obtener_monturas_random(db: Session = Depends(get_db)):
    """Retorna hasta 10 monturas aleatorias para secciones destacadas."""
    try:
        monturas = db.query(models.Montura)\
                     .filter(models.Montura.activo == True)\
                     .order_by(func.random())\
                     .limit(10)\
                     .all()
        
        resultado = []
        for m in monturas:
            resultado.append({
                "id": getattr(m, 'id', 0),
                "nombre": getattr(m, 'nombre', ''),
                "descripcion": getattr(m, 'descripcion', ''),
                "precio": float(getattr(m, 'precio', 0.0)),
                "talla": getattr(m, 'material', 'Acetato'),
                "categoria": getattr(m, 'categoria', 'Urbano'),
                "genero": getattr(m, 'genero', 'Unisex'),
                "marca": getattr(m, 'marca', 'Óptica Leb'),
                "imagen_url": getattr(m, 'imagen_url', ''),
                "stock": int(getattr(m, 'stock', 0)),
                "activo": bool(getattr(m, 'activo', True))
            })
        return resultado
    except Exception as e:
        print(f"Error en random: {e}")
        return []

@app.get("/api/zapatos")
def obtener_catalogo_monturas(db: Session = Depends(get_db)):
    """Retorna todas las monturas activas."""
    try:
        monturas = db.query(models.Montura).filter(models.Montura.activo == True).all()
        resultado = []
        for m in monturas:
            resultado.append({
                "id": getattr(m, 'id', 0),
                "nombre": getattr(m, 'nombre', ''),
                "descripcion": getattr(m, 'descripcion', ''),
                "precio": float(getattr(m, 'precio', 0.0)),
                "talla": getattr(m, 'material', 'Acetato'),
                "categoria": getattr(m, 'categoria', 'Urbano'),
                "genero": getattr(m, 'genero', 'Unisex'),
                "marca": getattr(m, 'marca', 'Óptica Leb'),
                "imagen_url": getattr(m, 'imagen_url', ''),
                "stock": int(getattr(m, 'stock', 0)),
                "activo": bool(getattr(m, 'activo', True))
            })
        return resultado
    except Exception as e:
        print(f"Error en catálogo: {e}")
        return []

@app.get("/api/zapatos/{montura_id}")
def obtener_montura_por_id(montura_id: int, db: Session = Depends(get_db)):
    montura = db.query(models.Montura).filter(models.Montura.id == montura_id, models.Montura.activo == True).first()
    if not montura:
        raise HTTPException(status_code=404, detail="Montura no encontrada")
    
    return {
        "id": getattr(montura, 'id', 0),
        "nombre": getattr(montura, 'nombre', ''),
        "descripcion": getattr(montura, 'descripcion', ''),
        "precio": float(getattr(montura, 'precio', 0.0)),
        "talla": getattr(montura, 'material', 'Acetato'),
        "categoria": getattr(montura, 'categoria', 'Urbano'),
        "genero": getattr(montura, 'genero', 'Unisex'),
        "marca": getattr(montura, 'marca', 'Óptica Leb'),
        "imagen_url": getattr(montura, 'imagen_url', ''),
        "stock": int(getattr(montura, 'stock', 0)),
        "activo": bool(getattr(montura, 'activo', True))
    }


# ==========================================
# ENDPOINTS DE CITAS Y AGENDAMIENTO
# ==========================================

@app.post("/api/ventas")
def crear_cita(cita: CitaCreate, db: Session = Depends(get_db)):
    """Registra una nueva solicitud de cita previa con validación de cupos y cliente recurrente."""
    try:
        citas_en_fecha = db.query(models.Cita).filter(
            models.Cita.fecha_cita == cita.fecha_cita,
            models.Cita.estado != "cancelada"
        ).count()

        if citas_en_fecha >= LIMITE_CITAS_DIARIAS:
            raise HTTPException(
                status_code=400, 
                detail=f"Lo sentimos, ya se ha alcanzado el límite de {LIMITE_CITAS_DIARIAS} citas agendadas para el día {cita.fecha_cita}. Por favor elija otra fecha."
            )

        citas_confirmadas_previas = db.query(models.Cita).filter(
            (models.Cita.cedula == cita.cedula) | (models.Cita.telefono == cita.telefono),
            models.Cita.estado == "confirmada"
        ).count()

        es_cliente_recurrente = citas_confirmadas_previas >= 2

        nueva_cita = models.Cita(
            nombre_cliente=cita.nombre_cliente,
            cedula=cita.cedula,
            telefono=cita.telefono,
            fecha_cita=cita.fecha_cita,
            montura_id=cita.montura_id,
            resumen_solicitud=cita.resumen_solicitud,
            monto_total=float(cita.monto_total or 0.00),
            estado="pendiente",
            es_recurrente=es_cliente_recurrente,
            usuario_id=cita.usuario_id
        )

        db.add(nueva_cita)
        db.commit()
        db.refresh(nueva_cita)

        return {
            "status": "ok", 
            "message": "Cita registrada con éxito", 
            "cita_id": nueva_cita.id,
            "es_recurrente": es_cliente_recurrente
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        print(f"Error al guardar cita: {e}")
        raise HTTPException(status_code=500, detail=f"Error en base de datos: {str(e)}")


@app.get("/api/admin/ventas")
def obtener_citas_admin(estado: str = Query("pendientes"), db: Session = Depends(get_db)):
    """Obtiene las citas filtradas por estado (pendientes o confirmadas)."""
    estado_normalizado = "pendiente" if "pendiente" in estado.lower() else "confirmada"
    
    try:
        citas_query = db.query(models.Cita).filter(models.Cita.estado == estado_normalizado)
        citas = citas_query.order_by(models.Cita.id.desc()).all()
        
        resultado = []
        for c in citas:
            resultado.append({
                "id": c.id,
                "nombre_cliente": c.nombre_cliente,
                "cedula": c.cedula,
                "telefono": c.telefono,
                "fecha_cita": str(c.fecha_cita),
                "monto_total": float(c.monto_total or 0.0),
                "resumen_pedido": c.resumen_solicitud,
                "estado": c.estado,
                "zapato_id": c.montura_id,
                "es_recurrente": c.es_recurrente,
                "fecha_venta": c.fecha_solicitud.isoformat() if c.fecha_solicitud else None
            })
            
        return resultado
    except Exception as e:
        print(f"Error al consultar citas: {e}")
        return []

@app.get("/api/admin/ventas/metricas")
def obtener_metricas_citas(periodo: str = Query("semana"), db: Session = Depends(get_db)):
    """Calcula las métricas generales de citas confirmadas."""
    try:
        citas_confirmadas = db.query(models.Cita).filter(models.Cita.estado == "confirmada").all()
        
        total_citas = len(citas_confirmadas)
        dinero_recaudado = sum(float(c.monto_total or 0.0) for c in citas_confirmadas)
        
        return {
            "total_ventas": total_citas,
            "dinero_recaudado": dinero_recaudado,
            "modelo_top": "Cita Oftalmológica"
        }
    except Exception as e:
        print(f"Error al calcular métricas: {e}")
        return {"total_ventas": 0, "dinero_recaudado": 0.0, "modelo_top": "N/A"}

@app.post("/api/admin/ventas/{cita_id}/confirmar")
def confirmar_cita(cita_id: int, db: Session = Depends(get_db)):
    """Confirma una cita pendiente, actualiza su estado y descuenta stock si incluyó montura."""
    cita = db.query(models.Cita).filter(models.Cita.id == cita_id).first()
    if not cita:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    
    if cita.estado == "confirmada":
        raise HTTPException(status_code=400, detail="Esta cita ya fue confirmada previamente")

    if cita.montura_id:
        montura = db.query(models.Montura).filter(models.Montura.id == cita.montura_id).first()
        if montura:
            if montura.stock > 0:
                montura.stock -= 1

    cita.estado = "confirmada"
    db.commit()
    return {"status": "ok", "message": "Cita confirmada exitosamente"}

@app.delete("/api/admin/ventas/{cita_id}/cancelar")
def cancelar_cita(cita_id: int, db: Session = Depends(get_db)):
    """Cancela y elimina una cita pendiente."""
    cita = db.query(models.Cita).filter(models.Cita.id == cita_id).first()
    if not cita:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    
    db.delete(cita)
    db.commit()
    return {"status": "ok", "message": "Cita cancelada y eliminada"}


# ==========================================
# ENDPOINT DE REPORTE PDF DE CITAS CUMPLIDAS
# ==========================================

@app.get("/api/admin/reporte-citas-pdf", response_class=HTMLResponse)
def generar_reporte_citas_pdf(periodo: str = Query("dia"), db: Session = Depends(get_db)):
    """Genera una vista HTML optimizada e imprimible para exportar a PDF las citas cumplidas (confirmadas)."""
    hoy = date.today()
    citas_query = db.query(models.Cita).filter(models.Cita.estado == "confirmada")

    titulo_periodo = "Reporte de Citas"

    if periodo == "dia":
        citas_query = citas_query.filter(models.Cita.fecha_cita == hoy)
        titulo_periodo = f"Citas Cumplidas del Día ({hoy.strftime('%d/%m/%Y')})"
    elif periodo == "semana":
        inicio_semana = hoy - timedelta(days=hoy.weekday())
        fin_semana = inicio_semana + timedelta(days=6)
        citas_query = citas_query.filter(models.Cita.fecha_cita >= inicio_semana, models.Cita.fecha_cita <= fin_semana)
        titulo_periodo = f"Citas Cumplidas de la Semana ({inicio_semana.strftime('%d/%m/%Y')} al {fin_semana.strftime('%d/%m/%Y')})"
    elif periodo == "mes":
        citas_query = citas_query.filter(
            func.extract('year', models.Cita.fecha_cita) == hoy.year,
            func.extract('month', models.Cita.fecha_cita) == hoy.month
        )
        titulo_periodo = f"Citas Cumplidas del Mes ({hoy.strftime('%B %Y')})"

    citas = citas_query.order_by(models.Cita.fecha_cita.asc()).all()
    total_recaudado = sum(float(c.monto_total or 0.0) for c in citas)

    html_content = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>{titulo_periodo} - Óptica Leb</title>
        <style>
            body {{ font-family: 'Inter', Arial, sans-serif; color: #1e293b; padding: 30px; margin: 0; }}
            .header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #0b1f36; padding-bottom: 15px; margin-bottom: 25px; }}
            .logo-text {{ font-size: 1.5rem; font-weight: bold; color: #0b1f36; }}
            .logo-text span {{ color: #0284c7; }}
            .report-info {{ text-align: right; font-size: 0.85rem; color: #64748b; }}
            h1 {{ font-size: 1.4rem; color: #0b1f36; margin-bottom: 5px; }}
            .subtitle {{ font-size: 0.9rem; color: #64748b; margin-bottom: 25px; }}
            table {{ width: 100%; border-collapse: collapse; margin-bottom: 25px; font-size: 0.85rem; }}
            th, td {{ border: 1px solid #cbd5e1; padding: 10px 12px; text-align: left; }}
            th {{ background-color: #0b1f36; color: white; text-transform: uppercase; font-size: 0.75rem; letter-spacing: 0.5px; }}
            tr:nth-child(even) {{ background-color: #f8fafc; }}
            .total-box {{ text-align: right; font-size: 1.1rem; font-weight: bold; color: #0b1f36; margin-top: 15px; }}
            .btn-print {{ background-color: #0284c7; color: white; border: none; padding: 10px 20px; font-size: 0.9rem; font-weight: bold; border-radius: 6px; cursor: pointer; margin-bottom: 20px; }}
            @media print {{ .btn-print {{ display: none; }} body {{ padding: 0; }} }}
        </style>
    </head>
    <body>
        <button class="btn-print" onclick="window.print()">🖨️ Imprimir / Guardar como PDF</button>
        
        <div class="header">
            <div class="logo-text">ÓPTICA<span>LEB</span></div>
            <div class="report-info">
                Fecha de Emisión: {datetime.now().strftime('%d/%m/%Y %H:%M')}<br>
                Sistema de Gestión de Citas
            </div>
        </div>

        <h1>{titulo_periodo}</h1>
        <div class="subtitle">Listado oficial de atenciones médicas y reservas completadas.</div>

        <table>
            <thead>
                <tr>
                    <th>ID</th>
                    <th>Paciente</th>
                    <th>Cédula</th>
                    <th>Teléfono</th>
                    <th>Fecha Cita</th>
                    <th>Detalle / Solicitud</th>
                    <th>Monto ($)</th>
                </tr>
            </thead>
            <tbody>
    """

    if not citas:
        html_content += """
                <tr>
                    <td colspan="7" style="text-align: center; color: #64748b; padding: 20px;">No se registraron citas cumplidas en este período.</td>
                </tr>
        """
    else:
        for c in citas:
            html_content += f"""
                <tr>
                    <td>{c.id}</td>
                    <td><strong>{c.nombre_cliente}</strong></td>
                    <td>{c.cedula}</td>
                    <td>{c.telefono}</td>
                    <td>{c.fecha_cita}</td>
                    <td>{c.resumen_solicitud}</td>
                    <td>${float(c.monto_total or 0.0):.2f}</td>
                </tr>
            """

    html_content += f"""
            </tbody>
        </table>

        <div class="total-box">
            Total Recaudado en el Período: ${total_recaudado:.2f}
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


# ==========================================
# CRUD ADMINISTRATIVO DE MONTURAS
# ==========================================

@app.get("/api/admin/zapatos")
def admin_obtener_monturas(db: Session = Depends(get_db)):
    return db.query(models.Montura).order_by(models.Montura.id.desc()).all()

@app.post("/api/admin/zapatos")
async def admin_crear_montura(
    nombre: str = Form(...),
    descripcion: Optional[str] = Form(None),
    precio: float = Form(...),
    talla: str = Form("Acetato"),
    categoria: Optional[str] = Form("Urbano"),
    genero: Optional[str] = Form("Unisex"),
    marca: Optional[str] = Form("Óptica Leb"),
    stock: int = Form(10),
    activo: str = Form("true"),
    imagen: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    imagen_url = None
    if imagen and imagen.filename:
        contenido = imagen.file.read()
        tipo = imagen.content_type or "image/jpeg"
        imagen_url = f"data:{tipo};base64," + base64.b64encode(contenido).decode("utf-8")

    es_activo = True if str(activo).lower() in ["true", "1", "on"] else False

    nueva_montura = models.Montura(
        nombre=nombre,
        descripcion=descripcion,
        precio=precio,
        material=talla,
        categoria=categoria,
        genero=genero,
        marca=marca,
        stock=stock,
        activo=es_activo,
        imagen_url=imagen_url
    )

    db.add(nueva_montura)
    db.commit()
    db.refresh(nueva_montura)
    return nueva_montura

@app.put("/api/admin/zapatos/{montura_id}")
async def admin_actualizar_montura(
    montura_id: int,
    nombre: str = Form(...),
    descripcion: Optional[str] = Form(None),
    precio: float = Form(...),
    talla: str = Form(...),
    categoria: Optional[str] = Form("Urbano"),
    genero: Optional[str] = Form("Unisex"),
    marca: Optional[str] = Form("Óptica Leb"),
    stock: int = Form(...),
    activo: str = Form("true"),
    imagen: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    montura = db.query(models.Montura).filter(models.Montura.id == montura_id).first()
    if not montura:
        raise HTTPException(status_code=404, detail="Montura no encontrada")

    if imagen and imagen.filename:
        contenido = imagen.file.read()
        tipo = imagen.content_type or "image/jpeg"
        montura.imagen_url = f"data:{tipo};base64," + base64.b64encode(contenido).decode("utf-8")

    montura.nombre = nombre
    montura.descripcion = descripcion
    montura.precio = precio
    montura.material = talla
    montura.categoria = categoria
    montura.genero = genero
    montura.marca = marca
    montura.stock = stock
    montura.activo = True if str(activo).lower() in ["true", "1", "on"] else False

    db.commit()
    db.refresh(montura)
    return montura

@app.delete("/api/admin/zapatos/{montura_id}")
def admin_eliminar_montura(montura_id: int, db: Session = Depends(get_db)):
    montura = db.query(models.Montura).filter(models.Montura.id == montura_id).first()
    if not montura:
        raise HTTPException(status_code=404, detail="Montura no encontrada")

    db.delete(montura)
    db.commit()
    return {"message": f"Montura con ID {montura_id} eliminada exitosamente", "status": "success"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)