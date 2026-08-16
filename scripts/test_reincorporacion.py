import os, sys
sys.path.insert(0, '.')
os.environ['GOOGLE_API_KEY'] = 'test_key'

import app.modules.users.models
import app.modules.users.docente.models
import app.modules.users.alumno.models
import app.modules.users.familiar.models
import app.modules.users.relacion_familiar.models
import app.modules.personal.models
import app.modules.enrollment.models
import app.modules.academic.models as ac_m
import app.modules.behavior.models
import app.modules.management.models
import app.modules.finance.models as fi_m
import app.modules.virtual.models

from app.db.database import SessionLocal
from app.modules.users.alumno.router import retirar_estudiante, reincorporar_estudiante
from app.modules.users.alumno.schemas import ReincorporarAlumnoRequest
from app.modules.admision.router import postular_alumno
from app.modules.admision.schemas import AdmisionPostulante
from app.modules.users.alumno.schemas import AlumnoCreate
from app.modules.users.familiar.schemas import FamiliarCreate
from fastapi import BackgroundTasks

db = SessionLocal()
admin_user = {"rol": "ADMIN", "id": 1}

print("=== 1. Probando flujo de Retiro y Reincorporación ===")
# Tomar un alumno de prueba
alumno = db.query(app.modules.users.alumno.models.Alumno).filter_by(estado_ingreso="ESTUDIANTE").first()
assert alumno is not None, "Debe haber al menos un alumno ESTUDIANTE"
al_id = alumno.id_alumno
print(f"Alumno seleccionado: ID {al_id} | {alumno.nombres} {alumno.apellidos} | DNI: {alumno.dni}")

# 1.1 Retirar alumno
res_ret = retirar_estudiante(id_alumno=al_id, db=db, current_user=admin_user)
db.refresh(alumno)
print(f"Estado tras retiro: {alumno.estado_ingreso}")
assert alumno.estado_ingreso == "RETIRADO"
if alumno.usuario:
    assert alumno.usuario.activo == False

# 1.2 Reincorporar alumno
# Obtener un grado válido
grado = db.query(ac_m.Grado).first()
datos_reinc = ReincorporarAlumnoRequest(id_grado=grado.id_grado, id_seccion=None, generar_pagos=True)
res_reinc = reincorporar_estudiante(id_alumno=al_id, datos=datos_reinc, db=db, current_user=admin_user)
db.refresh(alumno)
print(f"Estado tras reincorporación: {alumno.estado_ingreso}")
assert alumno.estado_ingreso == "ESTUDIANTE"
if alumno.usuario:
    assert alumno.usuario.activo == True
print("Resultado reincorporación:", res_reinc)

print("\n=== 2. Probando Readmisión de Alumno Retirado vía Web Pública ===")
# Retiramos de nuevo para probar la readmisión web
retirar_estudiante(id_alumno=al_id, db=db, current_user=admin_user)
db.refresh(alumno)
assert alumno.estado_ingreso == "RETIRADO"

# Postular con el mismo DNI
bg = BackgroundTasks()
postulacion = AdmisionPostulante(
    alumno=AlumnoCreate(
        dni=alumno.dni,
        nombres=alumno.nombres,
        apellidos=alumno.apellidos,
        fecha_nacimiento=alumno.fecha_nacimiento,
        genero="M",
        id_grado_ingreso=grado.id_grado
    ),
    familiar=FamiliarCreate(
        dni="88889999",
        nombres="Padre Test",
        apellidos="Familiar Test",
        telefono="999888777",
        email="padre@test.com",
        direccion="Calle Falsa 123"
    ),
    tipo_parentesco="PADRE"
)

res_post = postular_alumno(datos=postulacion, background_tasks=bg, db=db)
print("Resultado postulación readmisión:", res_post)
db.refresh(alumno)
print(f"Estado tras postular: {alumno.estado_ingreso}")
assert alumno.estado_ingreso == "POSTULANTE"

# Restaurar estado original a ESTUDIANTE
alumno.estado_ingreso = "ESTUDIANTE"
if alumno.usuario:
    alumno.usuario.activo = True
db.commit()

db.close()
print("\nTODOS LOS TESTS DE REINCORPORACIÓN Y READMISIÓN PASARON EXITOSAMENTE!")
