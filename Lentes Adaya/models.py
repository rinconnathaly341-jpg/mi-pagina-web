from sqlalchemy import Column, Integer, String, Numeric, Boolean, Text, TIMESTAMP, Date, func
from database import Base

class Montura(Base):
    __tablename__ = "monturas"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    descripcion = Column(Text, nullable=True)
    precio = Column(Numeric(10, 2), nullable=False)
    material = Column(String(50), nullable=False, default="Acetato")
    categoria = Column(String(50), nullable=True)
    genero = Column(String(20), default="Unisex")     
    marca = Column(String(50), default="Óptica Leb")   
    imagen_url = Column(Text, nullable=True)
    stock = Column(Integer, default=0)
    activo = Column(Boolean, default=True)
    creado_en = Column(TIMESTAMP(timezone=True), server_default=func.now())

class Cita(Base):
    __tablename__ = "citas"

    id = Column(Integer, primary_key=True, index=True)
    fecha_solicitud = Column(TIMESTAMP(timezone=True), server_default=func.now())
    
    nombre_cliente = Column(String(100), nullable=False)
    cedula = Column(String(30), nullable=False)
    telefono = Column(String(30), nullable=False)
    fecha_cita = Column(Date, nullable=False)
    
    estado = Column(String(20), default="pendiente")
    montura_id = Column(Integer, nullable=True)
    resumen_solicitud = Column(Text, nullable=False)
    monto_total = Column(Numeric(10, 2), default=0.00)
    es_recurrente = Column(Boolean, default=False)
    usuario_id = Column(Integer, nullable=True) # Para vincular la cita al cliente registrado si se desea

class UsuarioAdmin(Base):
    __tablename__ = "usuarios_admin"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    rol = Column(String(20), default="admin") # "super_admin" o "admin"

class UsuarioCliente(Base):
    __tablename__ = "usuarios_clientes"

    id = Column(Integer, primary_key=True, index=True)
    nombre_completo = Column(String(120), nullable=False)
    cedula = Column(String(30), unique=True, nullable=False)
    telefono = Column(String(30), nullable=False)
    correo = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    creado_en = Column(TIMESTAMP(timezone=True), server_default=func.now())