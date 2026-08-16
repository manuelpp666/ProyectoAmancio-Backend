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
import app.modules.academic.models
import app.modules.behavior.models
import app.modules.management.models
import app.modules.finance.models
import app.modules.virtual.models

from app.db.database import SessionLocal
from app.modules.enrollment.router import listar_no_renovados, procesar_retiro_no_renovados

db = SessionLocal()
admin_user = {"rol": "ADMIN", "id": 1}

print("=== 1. Probando listar_no_renovados ===")
res = listar_no_renovados(db=db, current_user=admin_user)
print("Año activo:", res.get("anio_activo"))
print("Año destino:", res.get("anio_destino"))
print("Estado inscripción:", res.get("inscripcion_estado"))
print("Fin inscripción:", res.get("fin_inscripcion"))
print("Total no renovados:", res.get("total_no_renovados"))

if res.get("alumnos"):
    sample = res["alumnos"][0]
    print(f"Ejemplo no renovado: ID {sample['id_alumno']} | {sample['nombre_completo']} | Grado: {sample['grado_actual']} | Sección: {sample['seccion_actual']}")
    
    # Test processing a single student in a test transaction or verifying logic
    target_id = sample['id_alumno']
    proc_res = procesar_retiro_no_renovados(payload={"ids_alumnos": [target_id]}, db=db, current_user=admin_user)
    print("Resultado procesar retiro:", proc_res)
    
    # Check that the student is now RETIRADO
    al = db.query(app.modules.users.alumno.models.Alumno).filter_by(id_alumno=target_id).first()
    print(f"Estado tras procesar: {al.estado_ingreso}")
    assert al.estado_ingreso == "RETIRADO"
    
    # Restore student back to ESTUDIANTE for test safety
    al.estado_ingreso = "ESTUDIANTE"
    if al.id_usuario:
        u = db.query(app.modules.users.models.Usuario).filter_by(id_usuario=al.id_usuario).first()
        if u:
            u.activo = True
    db.commit()
    print("Estudiante restaurado exitosamente.")

db.close()
print("\nTEST COMPLETED SUCCESSFULLY!")
