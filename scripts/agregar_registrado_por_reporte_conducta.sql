-- Quién registró cada reporte de conducta.
--
-- Hasta ahora el reporte no guardaba quién lo puso, y el alumno necesita saber
-- a qué auxiliar acudir si cree que el reporte está mal. Se guarda el nombre
-- escrito, igual que en reporte_conducta_eliminado: si ese auxiliar deja el
-- colegio, el reporte tiene que seguir diciendo quién fue.
--
-- Los reportes anteriores a este cambio quedan con estas columnas vacías: no
-- hay forma fiable de saber quién los registró, y el alumno ve "no registrado".
--
-- Se ejecuta UNA vez por base de datos (local y servidor). Es idempotente.
-- El backend funciona aunque todavía no se haya ejecutado: simplemente no
-- guarda ni muestra el nombre hasta que las columnas existan.

ALTER TABLE reporte_conducta
  ADD COLUMN IF NOT EXISTS id_usuario_registra INT(11)      DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS registrado_por      VARCHAR(200) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS rol_registra        VARCHAR(20)  DEFAULT NULL;
