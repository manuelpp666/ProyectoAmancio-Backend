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
from app.modules.users.alumno.router import listar_alumnos
from app.modules.enrollment.router import listar_matriculas
from app.modules.academic.router_notas import _base
from app.modules.virtual.router import obtener_sabana_notas
from app.modules.behavior.router import listar_notas_conducta, buscar_alumnos

db = SessionLocal()

# Reset student 1 if modified
st1 = db.query(app.modules.users.alumno.models.Alumno).filter_by(id_alumno=1).first()
if st1 and st1.estado_ingreso == "RETIRADO":
    st1.estado_ingreso = "ESTUDIANTE"
    db.commit()

print("=== 1. Selecting test student ===")
alumno = db.query(app.modules.users.alumno.models.Alumno).filter(
    app.modules.users.alumno.models.Alumno.estado_ingreso == "ESTUDIANTE"
).first()

matricula = db.query(app.modules.enrollment.models.Matricula).filter(
    app.modules.enrollment.models.Matricula.id_alumno == alumno.id_alumno,
    app.modules.enrollment.models.Matricula.id_anio_escolar == "2026"
).first()

id_seccion = matricula.id_seccion
id_grado = matricula.id_grado
id_alumno = alumno.id_alumno
print(f"Target student: ID {alumno.id_alumno} | {alumno.nombres} {alumno.apellidos} | DNI: {alumno.dni}")

carga = db.query(app.modules.management.models.CargaAcademica).filter(
    app.modules.management.models.CargaAcademica.id_seccion == id_seccion,
    app.modules.management.models.CargaAcademica.id_anio_escolar == "2026"
).first()

admin_user = {"rol": "ADMIN", "id": 1}
auxiliar_user = {"rol": "AUXILIAR", "id": 1}

try:
    print("\n--- Verifying student is present BEFORE retirement ---")
    # 1. Asistencia/Matricula
    mats_pre = listar_matriculas(anio_id="2026", seccion_id=id_seccion, db=db, current_user=auxiliar_user)
    al_ids_mats_pre = [m.id_alumno for m in mats_pre]
    assert id_alumno in al_ids_mats_pre, "Student should be in matriculas before retirement"
    print("  [OK] Present in /enrollment/matriculas/ (Asistencia)")

    # 2. Notas finales
    nf_pre = _base(db, "2026", None, None, id_seccion, None).all()
    nf_al_ids_pre = [row.id_alumno for row in nf_pre]
    assert id_alumno in nf_al_ids_pre, "Student should be in notas finales before retirement"
    print("  [OK] Present in /academic/notas-finales")

    # 3. Sabana docente
    if carga:
        sab_pre = obtener_sabana_notas(carga.id_carga_academica, 1, db=db, current_user={"rol": "DOCENTE", "id": carga.docente.id_usuario if carga.docente else 1})
        sab_al_ids_pre = [a["id_alumno"] for a in sab_pre["alumnos_notas"]]
        assert id_alumno in sab_al_ids_pre, "Student should be in sabana notas before retirement"
        print("  [OK] Present in /virtual/sabana-notas")

    # 4. Conducta
    cond_pre = listar_notas_conducta(anio="2026", bimestre=1, id_seccion=id_seccion, q="", pagina=1, por_pagina=100, db=db, current_user=auxiliar_user)
    cond_al_ids_pre = [a["id_alumno"] for a in cond_pre["alumnos"]]
    assert id_alumno in cond_al_ids_pre, "Student should be in conducta before retirement"
    print("  [OK] Present in /conducta/notas")

    # 5. Buscar alumnos
    busca_pre = buscar_alumnos(q=alumno.dni, db=db, current_user=auxiliar_user)
    busca_ids_pre = [a.id_alumno for a in busca_pre]
    assert id_alumno in busca_ids_pre, "Student should be searchable before retirement"
    print("  [OK] Present in /conducta/buscar-alumnos")

    print("\n=== 2. RETIRING STUDENT ===")
    alumno.estado_ingreso = "RETIRADO"
    db.commit()

    print("\n--- Verifying student is EXCLUDED AFTER retirement ---")
    # 1. Asistencia/Matricula
    mats_post = listar_matriculas(anio_id="2026", seccion_id=id_seccion, db=db, current_user=auxiliar_user)
    al_ids_mats_post = [m.id_alumno for m in mats_post]
    assert id_alumno not in al_ids_mats_post, "Retired student MUST NOT be in matriculas (asistencia)"
    print("  [OK] EXCLUDED from /enrollment/matriculas/ (Asistencia)")

    # 2. Notas finales y Libretas (SÍ debe figurar para poder emitir su libreta histórica)
    nf_post = _base(db, "2026", None, None, id_seccion, None).all()
    nf_al_ids_post = [row.id_alumno for row in nf_post]
    assert id_alumno in nf_al_ids_post, "Retired student SHOULD be present in historical notas finales/libretas"
    print("  [OK] Retained in /academic/notas-finales & Libretas for historical records")

    # 3. Sabana docente
    if carga:
        sab_post = obtener_sabana_notas(carga.id_carga_academica, 1, db=db, current_user={"rol": "DOCENTE", "id": carga.docente.id_usuario if carga.docente else 1})
        sab_al_ids_post = [a["id_alumno"] for a in sab_post["alumnos_notas"]]
        assert id_alumno not in sab_al_ids_post, "Retired student MUST NOT be in sabana notas"
        print("  [OK] EXCLUDED from /virtual/sabana-notas")

    # 4. Conducta
    cond_post = listar_notas_conducta(anio="2026", bimestre=1, id_seccion=id_seccion, q="", pagina=1, por_pagina=100, db=db, current_user=auxiliar_user)
    cond_al_ids_post = [a["id_alumno"] for a in cond_post["alumnos"]]
    assert id_alumno not in cond_al_ids_post, "Retired student MUST NOT be in conducta"
    print("  [OK] EXCLUDED from /conducta/notas")

    # 5. Buscar alumnos
    busca_post = buscar_alumnos(q=alumno.dni, db=db, current_user=auxiliar_user)
    busca_ids_post = [a.id_alumno for a in busca_post]
    assert id_alumno not in busca_ids_post, "Retired student MUST NOT be searchable"
    print("  [OK] EXCLUDED from /conducta/buscar-alumnos")

    # 6. Gestion estudiantes (El admin SÍ debe poder verlo con su estado RETIRADO)
    al_list_post = listar_alumnos(busqueda=alumno.dni, db=db, current_user=admin_user)
    al_list_ids_post = [a.id_alumno for a in al_list_post]
    assert id_alumno in al_list_ids_post, "Retired student SHOULD appear in admin list to see their RETIRADO status"
    print("  [OK] Visible in /alumnos/ (Gestion de Estudiantes) with status RETIRADO")

finally:
    # Always restore student back to ESTUDIANTE
    alumno.estado_ingreso = "ESTUDIANTE"
    db.commit()
    db.close()

print("\nALL VERIFICATIONS PASSED WITH 100% ACCURACY!")
