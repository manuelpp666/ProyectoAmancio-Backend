-- Historial de reportes de conducta eliminados.
--
-- Guarda una FOTO del reporte borrado (nombre del alumno, de la falta y los
-- puntos tal como estaban ese día) más el motivo, quién lo borró y cuándo.
-- Es una foto y no referencias porque el catálogo de faltas se puede editar y
-- borrar desde el panel del administrador: con solo los ids, el historial
-- acabaría mintiendo sobre lo que se borró.
--
-- Se ejecuta UNA vez por base de datos (local y servidor). Es idempotente.

CREATE TABLE IF NOT EXISTS reporte_conducta_eliminado (
  id_eliminado       INT(11)      NOT NULL AUTO_INCREMENT,
  id_reporte         INT(11)      NOT NULL,               -- id que tenía el reporte, informativo
  id_alumno          INT(11)      DEFAULT NULL,           -- sin FK a propósito: la foto sobrevive al alumno
  alumno             VARCHAR(200) DEFAULT NULL,
  dni                VARCHAR(15)  DEFAULT NULL,
  falta              VARCHAR(120) DEFAULT NULL,
  tipo_falta         VARCHAR(60)  DEFAULT NULL,
  puntos             INT(11)      NOT NULL DEFAULT 0,
  medida             VARCHAR(60)  DEFAULT NULL,
  cambio_ie          TINYINT(1)   NOT NULL DEFAULT 0,
  descripcion_suceso TEXT         DEFAULT NULL,
  fecha_reporte      DATETIME     DEFAULT NULL,
  motivo             VARCHAR(300) NOT NULL,
  id_usuario         INT(11)      DEFAULT NULL,           -- quién lo borró
  eliminado_por      VARCHAR(200) DEFAULT NULL,
  rol_elimina        VARCHAR(20)  DEFAULT NULL,
  fecha_eliminacion  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id_eliminado),
  KEY idx_rce_fecha (fecha_eliminacion),
  KEY idx_rce_alumno (id_alumno)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
