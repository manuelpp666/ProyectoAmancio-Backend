-- MariaDB dump 10.19  Distrib 10.4.32-MariaDB, for Win64 (AMD64)
--
-- Host: 127.0.0.1    Database: segunda_amancio_bd
-- ------------------------------------------------------
-- Server version	10.4.32-MariaDB

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `administrador`
--

DROP TABLE IF EXISTS `administrador`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `administrador` (
  `id_admin` int(11) NOT NULL AUTO_INCREMENT,
  `id_usuario` int(11) DEFAULT NULL,
  `dni` varchar(8) NOT NULL,
  `nombres` varchar(250) NOT NULL,
  `apellidos` varchar(250) NOT NULL,
  `telefono` varchar(9) DEFAULT NULL,
  `email` varchar(100) DEFAULT NULL,
  `url_perfil` varchar(255) DEFAULT NULL,
  `sueldo` decimal(10,2) DEFAULT 0.00,
  `permisos` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL COMMENT 'Estructura: {"finanzas": true, "cursos": {"ver": true, "horarios": true, "materias": false}}' CHECK (json_valid(`permisos`)),
  PRIMARY KEY (`id_admin`),
  UNIQUE KEY `dni` (`dni`),
  UNIQUE KEY `id_usuario` (`id_usuario`),
  CONSTRAINT `administrador_ibfk_1` FOREIGN KEY (`id_usuario`) REFERENCES `usuario` (`id_usuario`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `administrador`
--

LOCK TABLES `administrador` WRITE;
/*!40000 ALTER TABLE `administrador` DISABLE KEYS */;
INSERT INTO `administrador` VALUES (2,24,'81246124','Admin','Principal','029120480','admin@gmail.com',NULL,0.00,'{\"panel_control\": true, \"gestion_estudiantes\": true, \"gestion_personal\": true, \"tramites_finanzas\": true, \"chatbot\": true, \"mensajeria\": true, \"academico\": {\"estructura\": true, \"horarios\": true, \"docentes\": true, \"estudiantes\": true, \"cursos\": true}, \"contenido_web\": {\"info_general\": true, \"noticias\": true, \"calendario\": true}}');
/*!40000 ALTER TABLE `administrador` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `alumno`
--

DROP TABLE IF EXISTS `alumno`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `alumno` (
  `id_alumno` int(11) NOT NULL AUTO_INCREMENT,
  `id_usuario` int(11) DEFAULT NULL,
  `dni` varchar(8) NOT NULL,
  `nombres` varchar(250) NOT NULL,
  `apellidos` varchar(250) NOT NULL,
  `fecha_nacimiento` date DEFAULT NULL,
  `genero` varchar(1) DEFAULT NULL,
  `direccion` varchar(300) DEFAULT NULL,
  `enfermedad` varchar(150) DEFAULT NULL,
  `talla_polo` varchar(5) DEFAULT NULL,
  `colegio_procedencia` varchar(100) DEFAULT NULL,
  `id_grado_ingreso` int(11) DEFAULT NULL,
  `relacion_fraternal` tinyint(1) DEFAULT 0,
  `estado_ingreso` varchar(20) DEFAULT 'POSTULANTE',
  `motivo_rechazo` text DEFAULT NULL,
  `doc_dni_menor` varchar(500) DEFAULT NULL,
  `doc_dni_apoderado` varchar(500) DEFAULT NULL,
  `doc_fum` varchar(500) DEFAULT NULL,
  `doc_certificado_estudios` varchar(500) DEFAULT NULL,
  PRIMARY KEY (`id_alumno`),
  UNIQUE KEY `id_usuario` (`id_usuario`),
  KEY `fk_alumno_grado_ingreso` (`id_grado_ingreso`),
  CONSTRAINT `alumno_ibfk_1` FOREIGN KEY (`id_usuario`) REFERENCES `usuario` (`id_usuario`),
  CONSTRAINT `fk_alumno_grado_ingreso` FOREIGN KEY (`id_grado_ingreso`) REFERENCES `grado` (`id_grado`)
) ENGINE=InnoDB AUTO_INCREMENT=544 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `alumno`
--

LOCK TABLES `alumno` WRITE;
/*!40000 ALTER TABLE `alumno` DISABLE KEYS */;
INSERT INTO `alumno` VALUES (538,37,'12345678','Juanito','Alimaña',NULL,NULL,NULL,NULL,NULL,NULL,NULL,0,'ADMITIDO',NULL,NULL,NULL,NULL,NULL),(539,38,'10000001','Maria','Lopez Diaz','2014-05-10','F',NULL,NULL,NULL,NULL,6,0,'ADMITIDO',NULL,NULL,NULL,NULL,NULL),(540,39,'10000002','Carlos','Ruiz Vega','2014-08-22','M',NULL,NULL,NULL,NULL,6,0,'ADMITIDO',NULL,NULL,NULL,NULL,NULL),(541,40,'10000003','Ana','Torres Rios','2012-03-15','F',NULL,NULL,NULL,NULL,7,0,'ADMITIDO',NULL,NULL,NULL,NULL,NULL);
/*!40000 ALTER TABLE `alumno` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `anio_escolar`
--

DROP TABLE IF EXISTS `anio_escolar`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `anio_escolar` (
  `id_anio_escolar` char(6) NOT NULL,
  `fecha_inicio` date NOT NULL,
  `fecha_fin` date DEFAULT NULL,
  `activo` tinyint(1) DEFAULT 0,
  `tipo` varchar(20) NOT NULL DEFAULT 'REGULAR',
  `inicio_inscripcion` date DEFAULT NULL,
  `fin_inscripcion` date DEFAULT NULL,
  PRIMARY KEY (`id_anio_escolar`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `anio_escolar`
--

LOCK TABLES `anio_escolar` WRITE;
/*!40000 ALTER TABLE `anio_escolar` DISABLE KEYS */;
INSERT INTO `anio_escolar` VALUES ('2026','2026-03-09','2026-12-04',1,'REGULAR','2026-01-01','2026-10-10'),('2026-1','2026-01-01','2026-02-10',0,'VERANO',NULL,NULL);
/*!40000 ALTER TABLE `anio_escolar` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `area`
--

DROP TABLE IF EXISTS `area`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `area` (
  `id_area` int(11) NOT NULL AUTO_INCREMENT,
  `nombre` varchar(100) NOT NULL,
  PRIMARY KEY (`id_area`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `area`
--

LOCK TABLES `area` WRITE;
/*!40000 ALTER TABLE `area` DISABLE KEYS */;
INSERT INTO `area` VALUES (1,'Comunicaciones'),(2,'Matemáticas'),(3,'Ciencias'),(4,'Personal Social');
/*!40000 ALTER TABLE `area` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `asistencia`
--

DROP TABLE IF EXISTS `asistencia`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `asistencia` (
  `id_asistencia` int(11) NOT NULL AUTO_INCREMENT,
  `id_matricula` int(11) DEFAULT NULL,
  `fecha` date NOT NULL,
  `estado` enum('P','T','F','J') NOT NULL,
  `observacion` varchar(150) DEFAULT NULL,
  PRIMARY KEY (`id_asistencia`),
  UNIQUE KEY `uq_asistencia_matricula_fecha` (`id_matricula`,`fecha`),
  KEY `id_matricula` (`id_matricula`),
  KEY `idx_asistencia_fecha` (`fecha`),
  CONSTRAINT `asistencia_ibfk_1` FOREIGN KEY (`id_matricula`) REFERENCES `matricula` (`id_matricula`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `asistencia`
--

LOCK TABLES `asistencia` WRITE;
/*!40000 ALTER TABLE `asistencia` DISABLE KEYS */;
/*!40000 ALTER TABLE `asistencia` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `auxiliar`
--

DROP TABLE IF EXISTS `auxiliar`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `auxiliar` (
  `id_auxiliar` int(11) NOT NULL AUTO_INCREMENT,
  `id_usuario` int(11) DEFAULT NULL,
  `dni` varchar(8) NOT NULL,
  `nombres` varchar(250) NOT NULL,
  `apellidos` varchar(250) NOT NULL,
  `telefono` varchar(9) DEFAULT NULL,
  `email` varchar(100) DEFAULT NULL,
  `sueldo` decimal(10,2) DEFAULT 0.00,
  PRIMARY KEY (`id_auxiliar`),
  UNIQUE KEY `dni` (`dni`),
  UNIQUE KEY `id_usuario` (`id_usuario`),
  CONSTRAINT `auxiliar_ibfk_1` FOREIGN KEY (`id_usuario`) REFERENCES `usuario` (`id_usuario`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `auxiliar`
--

LOCK TABLES `auxiliar` WRITE;
/*!40000 ALTER TABLE `auxiliar` DISABLE KEYS */;
INSERT INTO `auxiliar` VALUES (1,33,'12131415','Auxiliar','en proceso','922265597','jesusleonardoh1@gmail.com',0.00);
/*!40000 ALTER TABLE `auxiliar` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `bitacora_admin`
--

DROP TABLE IF EXISTS `bitacora_admin`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `bitacora_admin` (
  `id_bitacora` int(11) NOT NULL AUTO_INCREMENT,
  `id_usuario` int(11) NOT NULL,
  `seccion` varchar(100) NOT NULL,
  `accion` text NOT NULL,
  `fecha` timestamp NOT NULL DEFAULT current_timestamp(),
  `tipo_op` varchar(10) DEFAULT NULL,
  PRIMARY KEY (`id_bitacora`),
  KEY `id_usuario` (`id_usuario`),
  CONSTRAINT `bitacora_admin_ibfk_1` FOREIGN KEY (`id_usuario`) REFERENCES `usuario` (`id_usuario`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `bitacora_admin`
--

LOCK TABLES `bitacora_admin` WRITE;
/*!40000 ALTER TABLE `bitacora_admin` DISABLE KEYS */;
/*!40000 ALTER TABLE `bitacora_admin` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `carga_academica`
--

DROP TABLE IF EXISTS `carga_academica`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `carga_academica` (
  `id_carga_academica` int(11) NOT NULL AUTO_INCREMENT,
  `id_anio_escolar` char(6) DEFAULT NULL,
  `id_seccion` int(11) DEFAULT NULL,
  `id_curso` int(11) DEFAULT NULL,
  `id_docente` int(11) DEFAULT NULL,
  PRIMARY KEY (`id_carga_academica`),
  KEY `id_anio_escolar` (`id_anio_escolar`),
  KEY `id_seccion` (`id_seccion`),
  KEY `id_curso` (`id_curso`),
  KEY `id_docente` (`id_docente`),
  CONSTRAINT `carga_academica_ibfk_1` FOREIGN KEY (`id_anio_escolar`) REFERENCES `anio_escolar` (`id_anio_escolar`),
  CONSTRAINT `carga_academica_ibfk_2` FOREIGN KEY (`id_seccion`) REFERENCES `seccion` (`id_seccion`),
  CONSTRAINT `carga_academica_ibfk_3` FOREIGN KEY (`id_curso`) REFERENCES `curso` (`id_curso`),
  CONSTRAINT `carga_academica_ibfk_4` FOREIGN KEY (`id_docente`) REFERENCES `docente` (`id_docente`)
) ENGINE=InnoDB AUTO_INCREMENT=16 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `carga_academica`
--

LOCK TABLES `carga_academica` WRITE;
/*!40000 ALTER TABLE `carga_academica` DISABLE KEYS */;
INSERT INTO `carga_academica` VALUES (10,'2026',7,4,3),(11,'2026',7,5,4),(12,'2026',7,6,3),(13,'2026',7,7,3),(14,'2026',9,5,4),(15,'2026',9,4,3);
/*!40000 ALTER TABLE `carga_academica` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `chatbot`
--

DROP TABLE IF EXISTS `chatbot`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `chatbot` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `filename` varchar(255) NOT NULL,
  `unique_filename` varchar(255) NOT NULL,
  `file_path` varchar(500) NOT NULL,
  `file_type` varchar(50) DEFAULT NULL,
  `pinecone_index` varchar(100) DEFAULT NULL,
  `total_chunks` int(11) DEFAULT 0,
  `status` enum('procesando','entrenado','error') DEFAULT 'procesando',
  `fecha_creacion` datetime DEFAULT current_timestamp(),
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `chatbot`
--

LOCK TABLES `chatbot` WRITE;
/*!40000 ALTER TABLE `chatbot` DISABLE KEYS */;
/*!40000 ALTER TABLE `chatbot` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `cita_psicologia`
--

DROP TABLE IF EXISTS `cita_psicologia`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `cita_psicologia` (
  `id_cita` int(11) NOT NULL AUTO_INCREMENT,
  `id_alumno` int(11) DEFAULT NULL,
  `id_familiar` int(11) DEFAULT NULL,
  `motivo` varchar(200) NOT NULL,
  `fecha_cita` datetime NOT NULL,
  `estado` varchar(20) DEFAULT 'PROGRAMADA',
  `resultado_reunion` text DEFAULT NULL,
  PRIMARY KEY (`id_cita`),
  KEY `id_alumno` (`id_alumno`),
  KEY `id_familiar` (`id_familiar`),
  CONSTRAINT `cita_psicologia_ibfk_1` FOREIGN KEY (`id_alumno`) REFERENCES `alumno` (`id_alumno`),
  CONSTRAINT `cita_psicologia_ibfk_2` FOREIGN KEY (`id_familiar`) REFERENCES `familiar` (`id_familiar`)
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `cita_psicologia`
--

LOCK TABLES `cita_psicologia` WRITE;
/*!40000 ALTER TABLE `cita_psicologia` DISABLE KEYS */;
INSERT INTO `cita_psicologia` VALUES (1,540,NULL,'Seguimiento por conducta critica y manejo de impulsos.','2026-06-26 09:30:00','PROGRAMADA',NULL),(2,539,NULL,'Acompanamiento emocional por ansiedad ante evaluaciones.','2026-06-26 11:00:00','PROGRAMADA',NULL),(3,538,434,'Entrevista con apoderado por bajo desempeno.','2026-06-26 15:00:00','PROGRAMADA',NULL),(4,541,NULL,'Orientacion vocacional.','2026-06-29 10:00:00','PROGRAMADA',NULL),(5,540,NULL,'Primera sesion de evaluacion conductual.','2026-06-03 10:00:00','COMPLETADA','El alumno muestra disposicion a mejorar. Se acordo plan de seguimiento semanal.'),(6,539,NULL,'Sesion de contencion emocional.','2026-06-06 12:00:00','COMPLETADA','Se brindaron tecnicas de respiracion. Mejoria notable en su animo.');
/*!40000 ALTER TABLE `cita_psicologia` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `clase_virtual`
--

DROP TABLE IF EXISTS `clase_virtual`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `clase_virtual` (
  `id_clase_virtual` int(11) NOT NULL AUTO_INCREMENT,
  `id_carga_academica` int(11) DEFAULT NULL,
  `tema` varchar(150) DEFAULT NULL,
  `fecha` datetime NOT NULL,
  `enlace` varchar(500) NOT NULL,
  `fecha_creacion` datetime DEFAULT current_timestamp(),
  PRIMARY KEY (`id_clase_virtual`),
  KEY `fk_clasevirtual_carga` (`id_carga_academica`),
  CONSTRAINT `fk_clasevirtual_carga` FOREIGN KEY (`id_carga_academica`) REFERENCES `carga_academica` (`id_carga_academica`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `clase_virtual`
--

LOCK TABLES `clase_virtual` WRITE;
/*!40000 ALTER TABLE `clase_virtual` DISABLE KEYS */;
INSERT INTO `clase_virtual` VALUES (1,10,NULL,'2026-07-31 14:30:00','https://meet.google.com/vou-exqx-abz','2026-07-29 23:18:30'),(2,10,'hola como estas','2026-07-30 18:30:00','https://meet.google.com/vou-exqx-abz','2026-07-29 23:23:20');
/*!40000 ALTER TABLE `clase_virtual` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `conversacion`
--

DROP TABLE IF EXISTS `conversacion`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `conversacion` (
  `id_conversacion` int(11) NOT NULL AUTO_INCREMENT,
  `usuario1_id` int(11) NOT NULL,
  `usuario2_id` int(11) NOT NULL,
  `ultimo_mensaje` text DEFAULT NULL,
  `fecha_actualizacion` datetime DEFAULT current_timestamp(),
  PRIMARY KEY (`id_conversacion`),
  UNIQUE KEY `usuario1_id` (`usuario1_id`,`usuario2_id`),
  KEY `usuario2_id` (`usuario2_id`),
  CONSTRAINT `conversacion_ibfk_1` FOREIGN KEY (`usuario1_id`) REFERENCES `usuario` (`id_usuario`),
  CONSTRAINT `conversacion_ibfk_2` FOREIGN KEY (`usuario2_id`) REFERENCES `usuario` (`id_usuario`)
) ENGINE=InnoDB AUTO_INCREMENT=9 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `conversacion`
--

LOCK TABLES `conversacion` WRITE;
/*!40000 ALTER TABLE `conversacion` DISABLE KEYS */;
INSERT INTO `conversacion` VALUES (7,24,37,NULL,'2026-05-25 00:46:07'),(8,42,37,NULL,'2026-07-16 17:40:49');
/*!40000 ALTER TABLE `conversacion` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `curso`
--

DROP TABLE IF EXISTS `curso`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `curso` (
  `id_curso` int(11) NOT NULL AUTO_INCREMENT,
  `id_area` int(11) DEFAULT NULL,
  `nombre` varchar(100) NOT NULL,
  `minutos_semanales` int(11) DEFAULT 0,
  `es_verano` tinyint(1) NOT NULL DEFAULT 0,
  `tipo_verano` varchar(20) DEFAULT NULL,
  `grupo_verano` varchar(20) DEFAULT NULL,
  PRIMARY KEY (`id_curso`),
  KEY `id_area` (`id_area`),
  CONSTRAINT `curso_ibfk_1` FOREIGN KEY (`id_area`) REFERENCES `area` (`id_area`)
) ENGINE=InnoDB AUTO_INCREMENT=9 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `curso`
--

LOCK TABLES `curso` WRITE;
/*!40000 ALTER TABLE `curso` DISABLE KEYS */;
INSERT INTO `curso` VALUES (4,1,'Comunicacion',240,0,NULL,NULL),(5,2,'Matematica',300,0,NULL,NULL),(6,3,'Ciencia y Tecnologia',180,0,NULL,NULL),(7,4,'Personal Social',120,0,NULL,NULL),(8,2,'Raz Mat',120,0,NULL,NULL);
/*!40000 ALTER TABLE `curso` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `curso_desaprobado`
--

DROP TABLE IF EXISTS `curso_desaprobado`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `curso_desaprobado` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `id_alumno` int(11) NOT NULL,
  `id_curso` int(11) NOT NULL,
  `id_anio_escolar` varchar(6) DEFAULT NULL,
  `nivel` varchar(20) DEFAULT NULL,
  `promedio` decimal(5,2) DEFAULT NULL,
  `recuperado` tinyint(1) NOT NULL DEFAULT 0,
  `id_anio_recuperado` varchar(6) DEFAULT NULL,
  `fecha` datetime DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_cd_alumno` (`id_alumno`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `curso_desaprobado`
--

LOCK TABLES `curso_desaprobado` WRITE;
/*!40000 ALTER TABLE `curso_desaprobado` DISABLE KEYS */;
/*!40000 ALTER TABLE `curso_desaprobado` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `docente`
--

DROP TABLE IF EXISTS `docente`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `docente` (
  `id_docente` int(11) NOT NULL AUTO_INCREMENT,
  `id_usuario` int(11) DEFAULT NULL,
  `dni` varchar(8) NOT NULL,
  `nombres` varchar(250) NOT NULL,
  `apellidos` varchar(250) NOT NULL,
  `especialidad` varchar(100) DEFAULT NULL,
  `descripcion` text DEFAULT NULL,
  `telefono` varchar(9) DEFAULT NULL,
  `email` varchar(100) DEFAULT NULL,
  `url_perfil` varchar(255) DEFAULT NULL,
  `sueldo` decimal(10,2) DEFAULT 0.00,
  `visible_web` tinyint(1) NOT NULL DEFAULT 1,
  PRIMARY KEY (`id_docente`),
  UNIQUE KEY `dni` (`dni`),
  UNIQUE KEY `id_usuario` (`id_usuario`),
  CONSTRAINT `docente_ibfk_1` FOREIGN KEY (`id_usuario`) REFERENCES `usuario` (`id_usuario`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `docente`
--

LOCK TABLES `docente` WRITE;
/*!40000 ALTER TABLE `docente` DISABLE KEYS */;
INSERT INTO `docente` VALUES (3,32,'72640066','Leonardo','Hernandez',NULL,NULL,'922265597','jesusleonardoh1@gmail.com',NULL,0.00,1),(4,41,'70111222','Lucia','Mendoza Paredes','Matematicas',NULL,'987654321','lucia.mendoza@amancio.edu.pe',NULL,2500.00,1);
/*!40000 ALTER TABLE `docente` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `drive_clases`
--

DROP TABLE IF EXISTS `drive_clases`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `drive_clases` (
  `id_carga_academica` int(11) NOT NULL,
  `url` varchar(500) NOT NULL,
  PRIMARY KEY (`id_carga_academica`),
  CONSTRAINT `fk_driveclases_carga` FOREIGN KEY (`id_carga_academica`) REFERENCES `carga_academica` (`id_carga_academica`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `drive_clases`
--

LOCK TABLES `drive_clases` WRITE;
/*!40000 ALTER TABLE `drive_clases` DISABLE KEYS */;
INSERT INTO `drive_clases` VALUES (10,'https://drive.google.com/drive/folders/1fVDi4ziL3lswSW1CticdTeUIyhPhp4Tk?usp=drive_link');
/*!40000 ALTER TABLE `drive_clases` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `entrega_tarea`
--

DROP TABLE IF EXISTS `entrega_tarea`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `entrega_tarea` (
  `id_entrega` int(11) NOT NULL AUTO_INCREMENT,
  `id_tarea` int(11) DEFAULT NULL,
  `id_alumno` int(11) DEFAULT NULL,
  `archivo_url` varchar(255) DEFAULT NULL,
  `comentario_alumno` text DEFAULT NULL,
  `fecha_envio` datetime DEFAULT current_timestamp(),
  `calificacion` decimal(4,2) DEFAULT NULL,
  `retroalimentacion_docente` text DEFAULT NULL,
  PRIMARY KEY (`id_entrega`),
  UNIQUE KEY `id_tarea` (`id_tarea`,`id_alumno`),
  KEY `id_alumno` (`id_alumno`),
  CONSTRAINT `entrega_tarea_ibfk_1` FOREIGN KEY (`id_tarea`) REFERENCES `tarea` (`id_tarea`),
  CONSTRAINT `entrega_tarea_ibfk_2` FOREIGN KEY (`id_alumno`) REFERENCES `alumno` (`id_alumno`)
) ENGINE=InnoDB AUTO_INCREMENT=18 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `entrega_tarea`
--

LOCK TABLES `entrega_tarea` WRITE;
/*!40000 ALTER TABLE `entrega_tarea` DISABLE KEYS */;
INSERT INTO `entrega_tarea` VALUES (17,8,538,'/media/entregas_tareas/tarea_8/alu_538_61215400.jpg',NULL,'2026-06-18 20:33:27',15.00,'falto menos IA');
/*!40000 ALTER TABLE `entrega_tarea` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `evaluacion_final`
--

DROP TABLE IF EXISTS `evaluacion_final`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `evaluacion_final` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `id_alumno` int(11) NOT NULL,
  `id_anio_escolar` varchar(6) DEFAULT NULL,
  `id_matricula` int(11) DEFAULT NULL,
  `nivel` varchar(20) DEFAULT NULL,
  `id_grado` int(11) DEFAULT NULL,
  `total_desaprobados` int(11) DEFAULT 0,
  `acumulado_desaprobados` int(11) DEFAULT 0,
  `resultado` varchar(20) DEFAULT 'PROMOVIDO',
  `correo_enviado` tinyint(1) NOT NULL DEFAULT 0,
  `fecha` datetime DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_ef_alumno` (`id_alumno`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `evaluacion_final`
--

LOCK TABLES `evaluacion_final` WRITE;
/*!40000 ALTER TABLE `evaluacion_final` DISABLE KEYS */;
/*!40000 ALTER TABLE `evaluacion_final` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `evento`
--

DROP TABLE IF EXISTS `evento`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `evento` (
  `id_evento` int(11) NOT NULL AUTO_INCREMENT,
  `id_anio_escolar` char(6) DEFAULT NULL,
  `titulo` varchar(150) NOT NULL,
  `descripcion` text DEFAULT NULL,
  `fecha_inicio` datetime NOT NULL,
  `fecha_fin` datetime DEFAULT NULL,
  `tipo_evento` varchar(50) DEFAULT NULL,
  `color` varchar(20) DEFAULT NULL,
  `activo` tinyint(1) DEFAULT 1,
  PRIMARY KEY (`id_evento`),
  KEY `fk_evento_anio` (`id_anio_escolar`),
  CONSTRAINT `fk_evento_anio` FOREIGN KEY (`id_anio_escolar`) REFERENCES `anio_escolar` (`id_anio_escolar`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=13 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `evento`
--

LOCK TABLES `evento` WRITE;
/*!40000 ALTER TABLE `evento` DISABLE KEYS */;
INSERT INTO `evento` VALUES (9,'2026','Inicio de clases','Primer día del año escolar.','2026-03-09 08:00:00',NULL,'Ceremonia','#093E7A',1),(10,'2026','Examen Bimestral I','Evaluaciones del primer bimestre.','2026-05-12 08:00:00','2026-05-16 13:00:00','Festividades','#701C32',1),(11,'2026','Día del Logro','Presentación de proyectos de los estudiantes.','2026-07-18 09:00:00',NULL,'Actividad','#059669',1),(12,'2026','Fiestas Patrias','Feriado nacional por aniversario patrio.','2026-07-28 00:00:00','2026-07-29 00:00:00','Feriado','#D97706',1);
/*!40000 ALTER TABLE `evento` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `exoneracion`
--

DROP TABLE IF EXISTS `exoneracion`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `exoneracion` (
  `id_exoneracion` int(11) NOT NULL AUTO_INCREMENT,
  `id_matricula` int(11) DEFAULT NULL,
  `motivo` varchar(100) NOT NULL,
  `concepto_exonerado` varchar(50) NOT NULL,
  `porcentaje_descuento` decimal(5,2) DEFAULT 100.00,
  `fecha_aprobacion` datetime DEFAULT current_timestamp(),
  `activo` tinyint(1) DEFAULT 1,
  PRIMARY KEY (`id_exoneracion`),
  KEY `id_matricula` (`id_matricula`),
  CONSTRAINT `exoneracion_ibfk_1` FOREIGN KEY (`id_matricula`) REFERENCES `matricula` (`id_matricula`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `exoneracion`
--

LOCK TABLES `exoneracion` WRITE;
/*!40000 ALTER TABLE `exoneracion` DISABLE KEYS */;
/*!40000 ALTER TABLE `exoneracion` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `familiar`
--

DROP TABLE IF EXISTS `familiar`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `familiar` (
  `id_familiar` int(11) NOT NULL AUTO_INCREMENT,
  `dni` varchar(40) DEFAULT NULL,
  `nombres` varchar(250) NOT NULL,
  `apellidos` varchar(250) NOT NULL,
  `telefono` varchar(9) DEFAULT NULL,
  `email` varchar(150) DEFAULT NULL,
  `direccion` varchar(300) DEFAULT NULL,
  PRIMARY KEY (`id_familiar`)
) ENGINE=InnoDB AUTO_INCREMENT=437 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `familiar`
--

LOCK TABLES `familiar` WRITE;
/*!40000 ALTER TABLE `familiar` DISABLE KEYS */;
INSERT INTO `familiar` VALUES (434,'87654321','Pepito','Perez','234565433','jesusleonardoh1@gmail.com','Block 15');
/*!40000 ALTER TABLE `familiar` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `grado`
--

DROP TABLE IF EXISTS `grado`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `grado` (
  `id_grado` int(11) NOT NULL AUTO_INCREMENT,
  `id_nivel` int(11) DEFAULT NULL,
  `nombre` varchar(20) NOT NULL,
  `orden` int(11) NOT NULL,
  PRIMARY KEY (`id_grado`),
  KEY `id_nivel` (`id_nivel`),
  CONSTRAINT `grado_ibfk_1` FOREIGN KEY (`id_nivel`) REFERENCES `nivel` (`id_nivel`)
) ENGINE=InnoDB AUTO_INCREMENT=12 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `grado`
--

LOCK TABLES `grado` WRITE;
/*!40000 ALTER TABLE `grado` DISABLE KEYS */;
INSERT INTO `grado` VALUES (1,1,'1ero Primaria',1),(2,1,'2do Primaria',2),(3,1,'3ero Primaria',3),(4,1,'4to Primaria',4),(5,1,'5to Primaria',5),(6,1,'6to Primaria',6),(7,2,'1ero Secundaria',1),(8,2,'2do Secundaria',2),(9,2,'3ro Secundaria',3),(10,2,'4to Secundaria',4),(11,2,'5to Secundaria',5);
/*!40000 ALTER TABLE `grado` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `hora_lectiva`
--

DROP TABLE IF EXISTS `hora_lectiva`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `hora_lectiva` (
  `id_hora` int(11) NOT NULL AUTO_INCREMENT,
  `hora_inicio` time NOT NULL,
  `hora_fin` time NOT NULL,
  `tipo` enum('clase','receso') DEFAULT 'clase',
  PRIMARY KEY (`id_hora`)
) ENGINE=InnoDB AUTO_INCREMENT=20 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `hora_lectiva`
--

LOCK TABLES `hora_lectiva` WRITE;
/*!40000 ALTER TABLE `hora_lectiva` DISABLE KEYS */;
INSERT INTO `hora_lectiva` VALUES (15,'08:00:00','08:45:00','clase'),(16,'08:45:00','09:30:00','clase'),(17,'09:30:00','09:45:00','receso'),(18,'09:45:00','10:30:00','clase'),(19,'10:30:00','11:15:00','clase');
/*!40000 ALTER TABLE `hora_lectiva` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `horario_escolar`
--

DROP TABLE IF EXISTS `horario_escolar`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `horario_escolar` (
  `id_horario` int(11) NOT NULL AUTO_INCREMENT,
  `id_carga_academica` int(11) NOT NULL,
  `dia_semana` enum('Lunes','Martes','Miércoles','Jueves','Viernes','Sábado') NOT NULL,
  `hora_inicio` time NOT NULL,
  `hora_fin` time NOT NULL,
  PRIMARY KEY (`id_horario`),
  KEY `id_carga_academica` (`id_carga_academica`),
  CONSTRAINT `horario_escolar_ibfk_1` FOREIGN KEY (`id_carga_academica`) REFERENCES `carga_academica` (`id_carga_academica`)
) ENGINE=InnoDB AUTO_INCREMENT=45 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `horario_escolar`
--

LOCK TABLES `horario_escolar` WRITE;
/*!40000 ALTER TABLE `horario_escolar` DISABLE KEYS */;
INSERT INTO `horario_escolar` VALUES (38,10,'Lunes','07:30:00','08:20:00'),(39,11,'Lunes','08:20:00','09:10:00'),(40,12,'Lunes','09:10:00','10:00:00'),(41,13,'Martes','07:30:00','08:20:00'),(42,10,'Martes','08:20:00','09:10:00'),(43,14,'Lunes','07:30:00','08:20:00'),(44,15,'Lunes','08:20:00','09:10:00');
/*!40000 ALTER TABLE `horario_escolar` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `material_clase`
--

DROP TABLE IF EXISTS `material_clase`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `material_clase` (
  `id_material` int(11) NOT NULL AUTO_INCREMENT,
  `id_carga_academica` int(11) DEFAULT NULL,
  `titulo` varchar(150) NOT NULL,
  `descripcion` text DEFAULT NULL,
  `archivo_url` varchar(255) DEFAULT NULL,
  `bimestre` int(11) NOT NULL,
  `fecha_publicacion` datetime DEFAULT current_timestamp(),
  PRIMARY KEY (`id_material`),
  KEY `fk_material_carga` (`id_carga_academica`),
  CONSTRAINT `fk_material_carga` FOREIGN KEY (`id_carga_academica`) REFERENCES `carga_academica` (`id_carga_academica`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `material_clase`
--

LOCK TABLES `material_clase` WRITE;
/*!40000 ALTER TABLE `material_clase` DISABLE KEYS */;
INSERT INTO `material_clase` VALUES (1,10,'Diapositivas sobre la celula',NULL,'/media/materiales_clase/carga_10/mat_4374d5.pdf',1,'2026-06-18 09:37:35');
/*!40000 ALTER TABLE `material_clase` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `matricula`
--

DROP TABLE IF EXISTS `matricula`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `matricula` (
  `id_matricula` int(11) NOT NULL AUTO_INCREMENT,
  `id_anio_escolar` char(6) DEFAULT NULL,
  `id_alumno` int(11) DEFAULT NULL,
  `id_seccion` int(11) DEFAULT NULL,
  `fecha_matricula` datetime DEFAULT current_timestamp(),
  `estado` varchar(20) DEFAULT 'MATRICULADO',
  `tipo_matricula` varchar(20) DEFAULT 'REGULAR',
  `id_grado` int(11) NOT NULL,
  `condicion` varchar(20) DEFAULT 'NORMAL',
  PRIMARY KEY (`id_matricula`),
  UNIQUE KEY `id_anio_escolar` (`id_anio_escolar`,`id_alumno`),
  KEY `id_alumno` (`id_alumno`),
  KEY `id_seccion` (`id_seccion`),
  KEY `fk_grado_matricula` (`id_grado`),
  CONSTRAINT `fk_grado_matricula` FOREIGN KEY (`id_grado`) REFERENCES `grado` (`id_grado`),
  CONSTRAINT `matricula_ibfk_1` FOREIGN KEY (`id_anio_escolar`) REFERENCES `anio_escolar` (`id_anio_escolar`),
  CONSTRAINT `matricula_ibfk_2` FOREIGN KEY (`id_alumno`) REFERENCES `alumno` (`id_alumno`),
  CONSTRAINT `matricula_ibfk_3` FOREIGN KEY (`id_seccion`) REFERENCES `seccion` (`id_seccion`)
) ENGINE=InnoDB AUTO_INCREMENT=20 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `matricula`
--

LOCK TABLES `matricula` WRITE;
/*!40000 ALTER TABLE `matricula` DISABLE KEYS */;
INSERT INTO `matricula` VALUES (12,'2026',538,7,'2026-05-23 02:27:39','MATRICULADO','REGULAR',6,'NORMAL'),(17,'2026',539,8,'2026-05-23 22:42:56','MATRICULADO','REGULAR',6,'NORMAL'),(18,'2026',540,8,'2026-05-23 22:42:56','MATRICULADO','REGULAR',6,'NORMAL'),(19,'2026',541,9,'2026-05-23 22:42:56','MATRICULADO','REGULAR',7,'NORMAL');
/*!40000 ALTER TABLE `matricula` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `mensaje`
--

DROP TABLE IF EXISTS `mensaje`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `mensaje` (
  `id_mensaje` int(11) NOT NULL AUTO_INCREMENT,
  `id_conversacion` int(11) DEFAULT NULL,
  `remitente_id` int(11) NOT NULL,
  `contenido` text NOT NULL,
  `leido` tinyint(1) DEFAULT 0,
  `fecha_envio` datetime DEFAULT current_timestamp(),
  PRIMARY KEY (`id_mensaje`),
  KEY `id_conversacion` (`id_conversacion`),
  KEY `remitente_id` (`remitente_id`),
  CONSTRAINT `mensaje_ibfk_1` FOREIGN KEY (`id_conversacion`) REFERENCES `conversacion` (`id_conversacion`) ON DELETE CASCADE,
  CONSTRAINT `mensaje_ibfk_2` FOREIGN KEY (`remitente_id`) REFERENCES `usuario` (`id_usuario`)
) ENGINE=InnoDB AUTO_INCREMENT=30 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `mensaje`
--

LOCK TABLES `mensaje` WRITE;
/*!40000 ALTER TABLE `mensaje` DISABLE KEYS */;
/*!40000 ALTER TABLE `mensaje` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `nivel`
--

DROP TABLE IF EXISTS `nivel`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `nivel` (
  `id_nivel` int(11) NOT NULL AUTO_INCREMENT,
  `nombre` varchar(20) NOT NULL,
  PRIMARY KEY (`id_nivel`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `nivel`
--

LOCK TABLES `nivel` WRITE;
/*!40000 ALTER TABLE `nivel` DISABLE KEYS */;
INSERT INTO `nivel` VALUES (1,'Primaria'),(2,'Secundaria'),(3,'Pre Academia');
/*!40000 ALTER TABLE `nivel` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `nivel_conducta`
--

DROP TABLE IF EXISTS `nivel_conducta`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `nivel_conducta` (
  `id_nivel_conducta` int(11) NOT NULL AUTO_INCREMENT,
  `nombre` varchar(120) NOT NULL,
  `id_tipo_falta` int(11) NOT NULL,
  `puntos` int(11) NOT NULL,
  `medida` varchar(60) DEFAULT NULL,
  `cambio_ie` tinyint(1) NOT NULL DEFAULT 0,
  `descripcion` text DEFAULT NULL,
  PRIMARY KEY (`id_nivel_conducta`),
  KEY `fk_nivel_conducta_tipo_falta` (`id_tipo_falta`),
  CONSTRAINT `fk_nivel_conducta_tipo_falta` FOREIGN KEY (`id_tipo_falta`) REFERENCES `tipo_falta` (`id_tipo_falta`)
) ENGINE=InnoDB AUTO_INCREMENT=31 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `nivel_conducta`
--

LOCK TABLES `nivel_conducta` WRITE;
/*!40000 ALTER TABLE `nivel_conducta` DISABLE KEYS */;
INSERT INTO `nivel_conducta` VALUES (5,'Inasistencia injustificada',1,3,NULL,0,'No asistir a la Institución Educativa injustificadamente.'),(6,'Tardanza al ingreso',1,2,NULL,0,'Llegar tarde a la Institución Educativa.'),(7,'Retraso a la formación o al aula',1,2,NULL,0,'Llegar retrasado a la formación o al aula.'),(8,'Evasión de la clase o la formación',1,4,'Acto reflexivo por 1 día',0,'Evadirse de la clase o la formación. Acto reflexivo por 1 día.'),(9,'Daño al mobiliario o infraestructura',2,8,'Acto reparador del daño',0,'Malograr el mobiliario o infraestructura de la I.E., hacer inscripciones, dibujos o textos deshonestos y otros. Acto reparador al daño cometido.'),(10,'Falta de respeto a los símbolos patrios',3,3,NULL,0,'Falta de respeto a los símbolos patrios.'),(11,'Inasistencia o interrupción de actividades cívicas',3,5,NULL,0,'No asistir o interrumpir las actividades cívico-patrióticas y otras de carácter institucional o público.'),(12,'Incumplir funciones como elemento de apoyo',3,3,NULL,0,'No cumplir sus funciones como elemento de apoyo: directivo, autoridades escolares, escolta e integrantes de talleres, etc.'),(13,'Incumplir actividades de promoción comunal',3,3,NULL,0,'No cumplir con las actividades de promoción comunal previstas.'),(14,'Apropiación de bienes ajenos',4,20,'Cambio de I.E.',1,'Apoderarse ilegalmente de las cosas de sus compañeros(as), de los docentes y de todo trabajador de la I.E. Cambio de I.E.'),(15,'Fraude o engaño a la autoridad educativa',4,8,'Acto reflexivo por 3 días',0,'Cometer fraude y/o mentir, tratar de engañar o sorprender al profesor o alguna autoridad educativa. Acto reflexivo por 3 días.'),(16,'Introducir juegos de azar o elementos distractores',4,5,NULL,0,'Introducir a la I.E. juegos de azar (casinos, dados) y otros elementos distractores (celulares, tablets, iPod, radios). Se decomisa y se devuelve por primera vez al apoderado; si reincide, se entrega el día de la clausura.'),(17,'Salir o ingresar a clases sin autorización',4,2,NULL,0,'Salir de clases o ingresar sin autorización.'),(18,'Encubrir la falta de un compañero',4,5,NULL,0,'Encubrir la falta de un compañero(a).'),(19,'Instigar actos de indisciplina',4,8,NULL,0,'Instigar actos de indisciplina en la I.E.'),(20,'Actitud de pareja portando el uniforme',4,10,'Acto reflexivo por 3 días',0,'Mostrar actitud de pareja estando con el uniforme. Acto reflexivo por 3 días.'),(21,'Pelear o promover riñas',5,20,'Cambio de I.E.',1,'Pelear, promover riñas y/o desorden dentro del aula, área del plantel o fuera del mismo. Cambio de I.E.'),(22,'Vocabulario soez o acciones obscenas',5,10,'Acto reflexivo por 3 días',0,'Emplear vocabulario soez y realizar acciones obscenas contra la moral. Acto reflexivo por 3 días.'),(23,'No saludar a docentes y trabajadores',5,4,NULL,0,'No saludar a los profesores(as) y demás trabajadores dentro o fuera de la I.E.'),(24,'Falta de respeto a docentes o compañeros',5,10,'Acto reflexivo por 3 días',0,'Faltar el respeto al profesor o compañeros de aula. Acto reflexivo por 3 días.'),(25,'Interrumpir la clase sin autorización',5,3,NULL,0,'Interrumpir la clase sin autorización.'),(26,'Uniforme incompleto',5,4,NULL,0,'Llevar el uniforme incompleto.'),(27,'Cabello sin corte reglamentario',5,4,NULL,0,'No cortarse el cabello a 1 cm de modo parejo.'),(28,'Uñas sin cortar',5,4,NULL,0,'No cortarse las uñas.'),(29,'Uso del buzo en día no correspondiente',5,4,NULL,0,'Llevar el buzo cuando no le toca Educación Física.'),(30,'Falta de aseo personal, del uniforme o del aula',5,4,NULL,0,'No conservar el aseo personal, de su uniforme o de su aula.');
/*!40000 ALTER TABLE `nivel_conducta` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `nota`
--

DROP TABLE IF EXISTS `nota`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `nota` (
  `id_nota` int(11) NOT NULL AUTO_INCREMENT,
  `id_matricula` int(11) DEFAULT NULL,
  `id_curso` int(11) DEFAULT NULL,
  `bimestre` int(11) NOT NULL,
  `tipo_nota` varchar(20) DEFAULT 'PROMEDIO',
  `valor` decimal(4,2) NOT NULL,
  `fecha_registro` datetime DEFAULT current_timestamp(),
  PRIMARY KEY (`id_nota`),
  UNIQUE KEY `uq_nota_unica` (`id_matricula`,`id_curso`,`bimestre`,`tipo_nota`),
  KEY `id_matricula` (`id_matricula`),
  KEY `id_curso` (`id_curso`),
  CONSTRAINT `nota_ibfk_1` FOREIGN KEY (`id_matricula`) REFERENCES `matricula` (`id_matricula`),
  CONSTRAINT `nota_ibfk_2` FOREIGN KEY (`id_curso`) REFERENCES `curso` (`id_curso`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `nota`
--

LOCK TABLES `nota` WRITE;
/*!40000 ALTER TABLE `nota` DISABLE KEYS */;
/*!40000 ALTER TABLE `nota` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `noticia`
--

DROP TABLE IF EXISTS `noticia`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `noticia` (
  `id_noticia` int(11) NOT NULL AUTO_INCREMENT,
  `titulo` varchar(200) NOT NULL,
  `contenido` text NOT NULL,
  `fecha_publicacion` datetime DEFAULT current_timestamp(),
  `imagen_portada_url` varchar(255) DEFAULT NULL,
  `categoria` varchar(50) DEFAULT NULL,
  `activo` tinyint(1) DEFAULT 1,
  `id_autor` int(11) DEFAULT NULL,
  PRIMARY KEY (`id_noticia`),
  KEY `id_autor` (`id_autor`),
  CONSTRAINT `noticia_ibfk_1` FOREIGN KEY (`id_autor`) REFERENCES `usuario` (`id_usuario`)
) ENGINE=InnoDB AUTO_INCREMENT=9 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `noticia`
--

LOCK TABLES `noticia` WRITE;
/*!40000 ALTER TABLE `noticia` DISABLE KEYS */;
INSERT INTO `noticia` VALUES (2,'Inicio del año escolar 2026','Damos la bienvenida a todos nuestros estudiantes al nuevo año académico, lleno de retos y aprendizajes.','2026-03-09 08:00:00','https://images.unsplash.com/photo-1580582932707-520aed937b7b','texto',0,24),(3,'Feria de Ciencias 2026','Nuestros estudiantes presentaron proyectos innovadores ante toda la comunidad educativa.','2026-04-15 10:00:00','https://images.unsplash.com/photo-1567168544813-cc03465b4fa8','texto',0,24),(4,'Video institucional','Conoce nuestras instalaciones y nuestra propuesta educativa en este recorrido.','2026-05-01 09:00:00','https://www.youtube.com/watch?v=dQw4w9WgXcQ','video',0,24),(5,'Tecnología Educativa y Confort en IEP. AMANCIO VARONA de Tumán: Primaria - Secundaria - Academia','<p>Introducción a la institución educativa.</p>','2026-07-28 00:31:42','https://youtu.be/CV7k2g4YOtA?si=dCgkOJfHTP_XjmY7','video',1,24),(6,'Uniforme escolar, identidad escolar. IEP. AMANCIO VARONA 2026','<p>Información sobre el uniforme escolar y la identidad escolar.</p>','2026-07-28 22:49:00','https://youtu.be/RwxoI0D3wKE?si=_7pkgXAeo9H-xe7e','video',1,24),(7,'Equipo Directivo 2026 IEP. Amancio Varona de Tumán','<p><strong>Les presentamos al equipo directivo de este año académico 2026</strong></p><p></p>','2026-07-28 22:50:40','https://youtu.be/GHpOjsST2Pg?si=M9pVCcbjKzurI8Xs','video',1,24),(8,'Pizarras Interactivas QOMO de 75\" última generación','<p>Presentamos las actualizaciones de las nuevas pizarras para las aulas este 2026.</p>','2026-07-28 22:53:54','https://youtu.be/xAPHMAP6q8g?si=FAS5_MVCkHVOL-SQ','video',1,24);
/*!40000 ALTER TABLE `noticia` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `pagina_configuracion`
--

DROP TABLE IF EXISTS `pagina_configuracion`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `pagina_configuracion` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `seccion` varchar(50) NOT NULL COMMENT 'home, nosotros, footer',
  `clave` varchar(100) NOT NULL COMMENT 'Identificador unico del campo (ej: hero_titulo)',
  `valor` text NOT NULL COMMENT 'Contenido de texto, URL de imagen o JSON',
  `tipo` enum('text','rich_text','image','json') DEFAULT 'text' COMMENT 'Ayuda al frontend a saber cómo renderizar',
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `clave` (`clave`),
  KEY `idx_seccion` (`seccion`)
) ENGINE=InnoDB AUTO_INCREMENT=38 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `pagina_configuracion`
--

LOCK TABLES `pagina_configuracion` WRITE;
/*!40000 ALTER TABLE `pagina_configuracion` DISABLE KEYS */;
INSERT INTO `pagina_configuracion` VALUES (1,'inicio','hero_titulo','Formando líderes con valores','text','2026-05-24 08:13:55'),(2,'inicio','hero_subtitulo','Educación de excelencia para toda la familia','text','2026-05-24 08:13:55'),(3,'inicio','hero_imagen','https://res.cloudinary.com/dteucmell/video/upload/v1785216593/flrx6gx1zgovrbacp031.mp4','image','2026-07-28 05:29:46'),(4,'inicio','home_enfoques','[{\"titulo\":\"Humanístico\",\"descripcion\":\"Promovemos la formación en valores y el respeto por el prójimo, cultivando ciudadanos comprometidos con su comunidad y su fe.\",\"imagen\":\"https://res.cloudinary.com/dteucmell/image/upload/v1785298071/f1ecicucf434qcm7fqdz.png\",\"icon\":\"Beaker\",\"badge\":\"Lightbulb\"},{\"titulo\":\"Artístico \",\"descripcion\":\"Impulsamos la expresión creativa a través de la música, la danza y las artes, fortaleciendo la identidad cultural de nuestros estudiantes.\",\"imagen\":\"https://res.cloudinary.com/dteucmell/image/upload/v1785297967/dgv9lrofzvjvhb1nlyr1.jpg\",\"icon\":\"Beaker\",\"badge\":\"Lightbulb\"},{\"titulo\":\"Científico \",\"descripcion\":\"Fomentamos el pensamiento lógico y la curiosidad por la investigación, formando estudiantes capaces de resolver problemas con creatividad y rigor.\",\"imagen\":\"https://res.cloudinary.com/dteucmell/image/upload/v1785297933/obtedhmeejfqkbrrgnku.jpg\",\"icon\":\"Beaker\",\"badge\":\"Lightbulb\"},{\"titulo\":\"Deportivo\",\"descripcion\":\"Desarrollamos la disciplina y el trabajo en equipo mediante la práctica deportiva, formando estudiantes íntegros dentro y fuera de la cancha.\",\"imagen\":\"https://res.cloudinary.com/dteucmell/image/upload/v1785298244/tlearwcgmckbbxjpjqfm.jpg\",\"icon\":\"Beaker\",\"badge\":\"Lightbulb\"}]','json','2026-07-29 04:10:32'),(5,'inicio','home_niveles','[{\"titulo\":\"Primaria\",\"descripcion\":\"Brindamos una educación integral que fortalece las habilidades básicas y los valores, sentando las bases para el éxito académico de nuestros estudiantes.\",\"icon\":\"Baby\",\"imagen\":\"https://res.cloudinary.com/dteucmell/image/upload/v1785298381/n0m7xjx27adlcw5njeq4.jpg\"},{\"titulo\":\"Secundaria\",\"descripcion\":\"Preparamos a nuestros estudiantes con conocimientos sólidos y pensamiento crítico, acompañándolos en su formación integral y su proyecto de vida.\",\"icon\":\"GraduationCap\",\"imagen\":\"https://res.cloudinary.com/dteucmell/image/upload/v1785298399/vlcsivrwzozf9itujz6k.jpg\"},{\"titulo\":\"Academia PreU\",\"descripcion\":\"Reforzamos y potenciamos el nivel académico de nuestros estudiantes, preparándolos para enfrentar con éxito los exámenes de admisión a la universidad.\",\"icon\":\"Trophy\",\"imagen\":\"https://res.cloudinary.com/dteucmell/image/upload/v1785298421/bfkrm2pxttqp1fpcesoj.jpg\"}]','json','2026-07-29 04:19:16'),(6,'nosotros','nosotros_titulo','Nuestra Historia','text','2026-05-24 08:13:55'),(7,'nosotros','nosotros_contenido','La Corporación Educativa \"Amancio Varona\" de Tumán nació del compromiso con la educación de la comunidad tumaneña. Su recorrido comenzó con la Academia Preuniversitaria, que desde el año 2009 preparó con éxito a sus primeros ingresantes a la universidad. Sobre esa base, en noviembre de 2010 se fundó el colegio, ampliando su servicio educativo a los niveles de Primaria y Secundaria.\n\nNuestra institución lleva el nombre del recordado R.P. Amancio Varona Valdivielso, guía espiritual y maestro de Tumán, cuyo ejemplo de servicio inspira nuestra formación integral: científica, humanística, artística y deportiva, bajo el lema \"Estudio, Respeto y Disciplina\".\n\nBajo la dirección del Dr. Tomás Serquén Montehermozo, promotor y director, seguimos brindando una educación de calidad a través de nuestros niveles de Primaria, Secundaria y Academia Preuniversitaria (PreU), acompañando a nuestros estudiantes en cada etapa de su desarrollo académico y personal, y en su camino hacia la universidad.','text','2026-07-29 04:51:38'),(8,'nosotros','nosotros_imagen','https://res.cloudinary.com/dteucmell/image/upload/v1785289330/mjpqup2kviejdhz8vjfk.jpg','image','2026-07-29 01:42:12'),(9,'nosotros','mision','Brindamos una educación integral de calidad, acompañando a cada estudiante con material didáctico propio y el compromiso cercano de nuestros docentes, para desarrollar sus competencias y valores.','text','2026-07-29 04:34:51'),(10,'nosotros','vision','Ser la institución educativa líder de la región, reconocida por la excelencia de nuestros estudiantes y los logros alcanzados en concursos académicos y deportivos.','text','2026-07-29 04:34:51'),(11,'nosotros','nosotros_frase','\"Educación Integral de calidad, para la vida\"','text','2026-07-29 04:20:04'),(12,'nosotros','nosotros_frase_autor','Estudio - Respeto - Disciplina','text','2026-07-29 04:20:04'),(13,'footer','footer_direccion','Block 10 - 11001 Tumán (Primaria) / Casuarinas 1era Etapa 130 Tumán (Secundaria - Academia), Tumán, Peru','text','2026-07-29 04:41:07'),(14,'footer','footer_correo','contacto@amanciovarona.edu.pe','text','2026-05-24 08:13:55'),(15,'footer','footer_telefono','+51 970 944 025','text','2026-07-29 04:42:15'),(16,'footer','footer_descripcion','Institución educativa comprometida con la formación de líderes.','text','2026-05-24 08:13:55'),(17,'docentes','docentes_titulo','Nuestros Docentes','text','2026-05-24 08:49:06'),(18,'docentes','docentes_subtitulo','Contamos con un equipo de profesionales apasionados, dedicados a inspirar y guiar a cada estudiante en su camino hacia la excelencia.','text','2026-05-24 08:49:06'),(19,'docentes','docentes_imagen','','image','2026-07-29 04:38:22'),(20,'nosotros','nosotros_header_titulo','Nuestra Institución','text','2026-05-25 04:46:55'),(21,'nosotros','nosotros_header_desc','Conoce la historia, los valores y el compromiso que definen a la familia Amancista.','text','2026-05-24 09:00:13'),(22,'calendario','calendario_titulo','Calendario Academico','text','2026-07-28 05:48:17'),(23,'calendario','calendario_subtitulo','Consulta las fechas importantes y eventos del año escolar.','text','2026-07-29 04:39:09'),(24,'noticias','noticias_titulo','Noticias Amancistas','text','2026-05-24 09:00:13'),(25,'noticias','noticias_subtitulo','Mantente al d?a con los comunicados, logros y actividades de nuestra comunidad.','text','2026-05-24 09:00:13'),(26,'admision','admision_titulo','Proceso de Admisión','text','2026-05-24 09:30:49'),(27,'admision','admision_subtitulo','Completa los datos para iniciar la postulación de tu menor hijo(a).','text','2026-05-24 09:30:56'),(28,'footer','footer_facebook','https://www.facebook.com/IepAmancioVaronaTuman?_rdc=1&_rdr#','text','2026-07-29 01:43:58'),(29,'footer','footer_youtube','https://www.youtube.com/@corporacioneducativaamanci3463','text','2026-07-29 01:43:58'),(30,'footer','footer_tiktok','','text','2026-07-29 01:43:58'),(31,'nosotros','mision_imagen','https://res.cloudinary.com/dteucmell/image/upload/v1785299595/aefuspnhntmyssfj0njr.jpg','text','2026-07-29 04:34:51'),(32,'nosotros','vision_imagen','https://res.cloudinary.com/dteucmell/image/upload/v1785299599/sqpraqzevusi6t5vslaa.jpg','text','2026-07-29 04:34:51'),(33,'nosotros','himno_titulo','','text','2026-07-29 04:34:51'),(34,'nosotros','himno_contenido','','text','2026-07-29 04:34:51'),(35,'nosotros','nosotros_header_imagen','https://res.cloudinary.com/dteucmell/image/upload/v1785301295/siwqf89kxc4nu3oywq6z.jpg','text','2026-07-29 05:01:24'),(36,'login','login_imagen','https://res.cloudinary.com/dteucmell/image/upload/v1785386416/scctvh3wcbkfscqomi1t.jpg','text','2026-07-30 04:40:05'),(37,'academico','nota_minima_aprobatoria','11','text','2026-07-30 17:24:47');
/*!40000 ALTER TABLE `pagina_configuracion` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `pago`
--

DROP TABLE IF EXISTS `pago`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `pago` (
  `id_pago` int(11) NOT NULL AUTO_INCREMENT,
  `id_usuario` int(11) DEFAULT NULL,
  `id_alumno` int(11) NOT NULL,
  `id_matricula` int(11) DEFAULT NULL,
  `id_solicitud_tramite` int(11) DEFAULT NULL,
  `concepto` varchar(150) NOT NULL,
  `monto` decimal(10,2) NOT NULL,
  `mora` decimal(10,2) DEFAULT 0.00,
  `monto_total` decimal(10,2) NOT NULL,
  `codigo_operacion_bcp` varchar(50) DEFAULT NULL,
  `estado` varchar(20) DEFAULT 'PENDIENTE',
  `fecha_vencimiento` date DEFAULT NULL,
  `fecha_pago` datetime DEFAULT NULL,
  `json_respuesta_banco` text DEFAULT NULL,
  `id_tipo_pago` int(11) DEFAULT NULL,
  PRIMARY KEY (`id_pago`),
  KEY `id_usuario` (`id_usuario`),
  KEY `id_alumno` (`id_alumno`),
  KEY `id_matricula` (`id_matricula`),
  KEY `id_solicitud_tramite` (`id_solicitud_tramite`),
  KEY `fk_pago_tipopago` (`id_tipo_pago`),
  KEY `idx_pago_alumno_estado` (`id_alumno`,`estado`),
  CONSTRAINT `fk_pago_tipopago` FOREIGN KEY (`id_tipo_pago`) REFERENCES `tipo_pago` (`id_tipo_pago`),
  CONSTRAINT `pago_ibfk_1` FOREIGN KEY (`id_usuario`) REFERENCES `usuario` (`id_usuario`),
  CONSTRAINT `pago_ibfk_2` FOREIGN KEY (`id_alumno`) REFERENCES `alumno` (`id_alumno`),
  CONSTRAINT `pago_ibfk_3` FOREIGN KEY (`id_matricula`) REFERENCES `matricula` (`id_matricula`),
  CONSTRAINT `pago_ibfk_4` FOREIGN KEY (`id_solicitud_tramite`) REFERENCES `solicitud_tramite` (`id_solicitud_tramite`)
) ENGINE=InnoDB AUTO_INCREMENT=22 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `pago`
--

LOCK TABLES `pago` WRITE;
/*!40000 ALTER TABLE `pago` DISABLE KEYS */;
INSERT INTO `pago` VALUES (6,NULL,538,NULL,NULL,'Vacante - Juanito  Alimaña',100.00,0.00,100.00,'MANUAL-CAJA','PAGADO','2026-10-10','2026-05-23 02:27:39',NULL,9),(7,NULL,538,NULL,NULL,'Matricula - Juanito  Alimaña',200.00,0.00,200.00,'MANUAL-CAJA','PAGADO','2026-10-10','2026-05-23 02:27:54',NULL,10),(9,NULL,538,NULL,NULL,'PENSION MARZO 2026',250.00,5.00,255.00,NULL,'PENDIENTE','2026-03-30',NULL,NULL,11),(10,NULL,538,NULL,NULL,'PENSION ABRIL 2026',250.00,5.00,255.00,NULL,'PENDIENTE','2026-04-30',NULL,NULL,11),(11,NULL,538,NULL,NULL,'PENSION MAYO 2026',250.00,5.00,255.00,NULL,'PENDIENTE','2026-05-30',NULL,NULL,11),(12,NULL,538,NULL,NULL,'PENSION JUNIO 2026',250.00,5.00,255.00,NULL,'PENDIENTE','2026-06-30',NULL,NULL,11),(13,NULL,538,NULL,NULL,'PENSION JULIO 2026',250.00,0.00,250.00,NULL,'PENDIENTE','2026-07-30',NULL,NULL,11),(14,NULL,538,NULL,NULL,'PENSION AGOSTO 2026',250.00,0.00,250.00,NULL,'PENDIENTE','2026-08-30',NULL,NULL,11),(15,NULL,538,NULL,NULL,'PENSION SEPTIEMBRE 2026',250.00,0.00,250.00,NULL,'PENDIENTE','2026-09-30',NULL,NULL,11),(16,NULL,538,NULL,NULL,'PENSION OCTUBRE 2026',250.00,0.00,250.00,NULL,'PENDIENTE','2026-10-30',NULL,NULL,11),(17,NULL,538,NULL,NULL,'PENSION NOVIEMBRE 2026',250.00,0.00,250.00,NULL,'PENDIENTE','2026-11-30',NULL,NULL,11),(18,NULL,538,NULL,NULL,'PENSION DICIEMBRE 2026',250.00,0.00,250.00,NULL,'PENDIENTE','2026-12-30',NULL,NULL,11),(19,NULL,538,NULL,NULL,'Modulo 1',150.00,5.00,155.00,NULL,'PENDIENTE','2026-03-30',NULL,NULL,12),(20,37,538,NULL,8,'TRAMITE: Justificación de inasistencia (PeriodoAcademico.AMBOS)',10.00,0.00,10.00,'MANUAL-CAJA','PAGADO','2026-08-11','2026-07-30 00:16:33',NULL,NULL),(21,37,538,NULL,9,'TRAMITE: Justificación de inasistencia (PeriodoAcademico.AMBOS)',10.00,0.00,10.00,NULL,'PENDIENTE','2026-08-11',NULL,NULL,NULL);
/*!40000 ALTER TABLE `pago` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_general_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'NO_AUTO_VALUE_ON_ZERO' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`localhost`*/ /*!50003 TRIGGER `tr_matricular_tras_pago_vacante` AFTER UPDATE ON `pago` FOR EACH ROW BEGIN
    -- 1. Solo actuar si el estado cambió a PAGADO y NO era pagado antes
    IF NEW.estado = 'PAGADO' AND OLD.estado <> 'PAGADO' THEN
        
        -- 2. Solo actuar si el concepto menciona 'VACANTE'
        IF NEW.concepto LIKE '%VACANTE%' THEN
            
            INSERT INTO matricula (
                id_anio_escolar, 
                id_alumno, 
                id_grado, 
                fecha_matricula, 
                estado, 
                tipo_matricula
            )
            SELECT 
                ae.id_anio_escolar, 
                NEW.id_alumno, 
                al.id_grado_ingreso,
                NOW(), 
                'MATRICULADO', 
                ae.tipo -- Tomamos el tipo (REGULAR/VERANO) directamente del año escolar activo
            FROM anio_escolar ae
            JOIN alumno al ON al.id_alumno = NEW.id_alumno
            -- Buscamos el año donde hoy cae dentro del rango de inscripciones
            WHERE ae.activo = 1 
              AND CURDATE() BETWEEN ae.inicio_inscripcion AND ae.fin_inscripcion
            LIMIT 1;
            
        END IF;
    END IF;
END */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `plan_estudio`
--

DROP TABLE IF EXISTS `plan_estudio`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `plan_estudio` (
  `id_plan_estudio` int(11) NOT NULL AUTO_INCREMENT,
  `id_curso` int(11) DEFAULT NULL,
  `id_grado` int(11) DEFAULT NULL,
  PRIMARY KEY (`id_plan_estudio`),
  KEY `id_curso` (`id_curso`),
  KEY `id_grado` (`id_grado`),
  CONSTRAINT `plan_estudio_ibfk_1` FOREIGN KEY (`id_curso`) REFERENCES `curso` (`id_curso`),
  CONSTRAINT `plan_estudio_ibfk_2` FOREIGN KEY (`id_grado`) REFERENCES `grado` (`id_grado`)
) ENGINE=InnoDB AUTO_INCREMENT=28 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `plan_estudio`
--

LOCK TABLES `plan_estudio` WRITE;
/*!40000 ALTER TABLE `plan_estudio` DISABLE KEYS */;
INSERT INTO `plan_estudio` VALUES (11,4,6),(12,5,6),(13,6,6),(14,7,6),(15,4,7),(16,5,7),(17,6,7),(18,7,7),(21,8,7),(22,8,8),(23,8,9);
/*!40000 ALTER TABLE `plan_estudio` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `psicologo`
--

DROP TABLE IF EXISTS `psicologo`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `psicologo` (
  `id_psicologo` int(11) NOT NULL AUTO_INCREMENT,
  `id_usuario` int(11) DEFAULT NULL,
  `dni` varchar(8) NOT NULL,
  `nombres` varchar(250) NOT NULL,
  `apellidos` varchar(250) NOT NULL,
  `telefono` varchar(9) DEFAULT NULL,
  `email` varchar(100) DEFAULT NULL,
  `sueldo` decimal(10,2) DEFAULT 0.00,
  PRIMARY KEY (`id_psicologo`),
  UNIQUE KEY `dni` (`dni`),
  UNIQUE KEY `id_usuario` (`id_usuario`),
  CONSTRAINT `psicologo_ibfk_1` FOREIGN KEY (`id_usuario`) REFERENCES `usuario` (`id_usuario`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `psicologo`
--

LOCK TABLES `psicologo` WRITE;
/*!40000 ALTER TABLE `psicologo` DISABLE KEYS */;
INSERT INTO `psicologo` VALUES (1,42,'60415217','Gabriela','Serquen','999999999','gabrielitica20@gmail.com',0.00);
/*!40000 ALTER TABLE `psicologo` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `relacion_familiar`
--

DROP TABLE IF EXISTS `relacion_familiar`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `relacion_familiar` (
  `id_relacion_familiar` int(11) NOT NULL AUTO_INCREMENT,
  `id_alumno` int(11) DEFAULT NULL,
  `id_familiar` int(11) DEFAULT NULL,
  `tipo_parentesco` varchar(50) DEFAULT NULL,
  PRIMARY KEY (`id_relacion_familiar`),
  KEY `id_alumno` (`id_alumno`),
  KEY `id_familiar` (`id_familiar`),
  CONSTRAINT `relacion_familiar_ibfk_1` FOREIGN KEY (`id_alumno`) REFERENCES `alumno` (`id_alumno`) ON DELETE CASCADE,
  CONSTRAINT `relacion_familiar_ibfk_2` FOREIGN KEY (`id_familiar`) REFERENCES `familiar` (`id_familiar`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=532 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `relacion_familiar`
--

LOCK TABLES `relacion_familiar` WRITE;
/*!40000 ALTER TABLE `relacion_familiar` DISABLE KEYS */;
INSERT INTO `relacion_familiar` VALUES (528,538,434,'PADRE');
/*!40000 ALTER TABLE `relacion_familiar` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `reporte_conducta`
--

DROP TABLE IF EXISTS `reporte_conducta`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `reporte_conducta` (
  `id_reporte` int(11) NOT NULL AUTO_INCREMENT,
  `id_alumno` int(11) DEFAULT NULL,
  `id_docente` int(11) DEFAULT NULL,
  `id_nivel_conducta` int(11) DEFAULT NULL,
  `fecha_reporte` datetime DEFAULT current_timestamp(),
  `descripcion_suceso` text NOT NULL,
  `estado` varchar(20) DEFAULT 'REGISTRADO',
  PRIMARY KEY (`id_reporte`),
  KEY `id_alumno` (`id_alumno`),
  KEY `id_docente` (`id_docente`),
  KEY `id_nivel_conducta` (`id_nivel_conducta`),
  CONSTRAINT `reporte_conducta_ibfk_1` FOREIGN KEY (`id_alumno`) REFERENCES `alumno` (`id_alumno`),
  CONSTRAINT `reporte_conducta_ibfk_2` FOREIGN KEY (`id_docente`) REFERENCES `docente` (`id_docente`),
  CONSTRAINT `reporte_conducta_ibfk_3` FOREIGN KEY (`id_nivel_conducta`) REFERENCES `nivel_conducta` (`id_nivel_conducta`)
) ENGINE=InnoDB AUTO_INCREMENT=10 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `reporte_conducta`
--

LOCK TABLES `reporte_conducta` WRITE;
/*!40000 ALTER TABLE `reporte_conducta` DISABLE KEYS */;
INSERT INTO `reporte_conducta` VALUES (1,540,3,21,'2026-05-30 21:09:52','Agresion verbal reiterada a un companero en el aula.','REGISTRADO'),(2,540,4,21,'2026-06-07 21:09:52','Falta de respeto grave al docente durante la clase.','REGISTRADO'),(3,540,3,22,'2026-06-15 21:09:52','Dano intencional a material del laboratorio.','REGISTRADO'),(4,539,3,21,'2026-06-04 21:09:52','Ausencia injustificada a evaluacion programada.','REGISTRADO'),(5,539,4,22,'2026-06-13 21:09:52','Uso indebido del celular en hora de examen.','REGISTRADO'),(6,541,3,6,'2026-06-11 21:09:52','Llego tarde al inicio de la jornada.','REGISTRADO'),(7,538,4,19,'2026-06-09 21:09:52','No presento la tarea en la fecha indicada.','REGISTRADO');
/*!40000 ALTER TABLE `reporte_conducta` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `resumen_nota`
--

DROP TABLE IF EXISTS `resumen_nota`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `resumen_nota` (
  `id_resumen_notas` int(11) NOT NULL AUTO_INCREMENT,
  `id_matricula` int(11) DEFAULT NULL,
  `id_curso` int(11) DEFAULT NULL,
  `nota_bimestre1` decimal(5,2) DEFAULT NULL,
  `nota_bimestre2` decimal(5,2) DEFAULT NULL,
  `nota_bimestre3` decimal(5,2) DEFAULT NULL,
  `nota_bimestre4` decimal(5,2) DEFAULT NULL,
  `promedio_final` decimal(5,2) DEFAULT NULL,
  `estado_curso` varchar(20) DEFAULT 'EN CURSO',
  PRIMARY KEY (`id_resumen_notas`),
  KEY `id_matricula` (`id_matricula`),
  KEY `id_curso` (`id_curso`),
  CONSTRAINT `resumen_nota_ibfk_1` FOREIGN KEY (`id_matricula`) REFERENCES `matricula` (`id_matricula`),
  CONSTRAINT `resumen_nota_ibfk_2` FOREIGN KEY (`id_curso`) REFERENCES `curso` (`id_curso`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `resumen_nota`
--

LOCK TABLES `resumen_nota` WRITE;
/*!40000 ALTER TABLE `resumen_nota` DISABLE KEYS */;
/*!40000 ALTER TABLE `resumen_nota` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `seccion`
--

DROP TABLE IF EXISTS `seccion`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `seccion` (
  `id_seccion` int(11) NOT NULL AUTO_INCREMENT,
  `id_grado` int(11) NOT NULL,
  `nombre` varchar(5) NOT NULL,
  `vacantes` int(11) NOT NULL DEFAULT 30,
  `id_anio_escolar` char(6) NOT NULL,
  PRIMARY KEY (`id_seccion`),
  KEY `id_grado` (`id_grado`),
  KEY `fk_seccion_anio` (`id_anio_escolar`),
  CONSTRAINT `fk_seccion_anio` FOREIGN KEY (`id_anio_escolar`) REFERENCES `anio_escolar` (`id_anio_escolar`),
  CONSTRAINT `seccion_ibfk_1` FOREIGN KEY (`id_grado`) REFERENCES `grado` (`id_grado`)
) ENGINE=InnoDB AUTO_INCREMENT=12 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `seccion`
--

LOCK TABLES `seccion` WRITE;
/*!40000 ALTER TABLE `seccion` DISABLE KEYS */;
INSERT INTO `seccion` VALUES (7,6,'Azul',30,'2026'),(8,6,'Rojo',25,'2026'),(9,7,'A',30,'2026'),(10,7,'B',30,'2026'),(11,1,'Azul',30,'2026');
/*!40000 ALTER TABLE `seccion` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `solicitud_matricula`
--

DROP TABLE IF EXISTS `solicitud_matricula`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `solicitud_matricula` (
  `id_solicitud_matricula` int(11) NOT NULL AUTO_INCREMENT,
  `id_alumno` int(11) NOT NULL,
  `id_anio_escolar_origen` char(6) DEFAULT NULL,
  `anio_destino` varchar(6) NOT NULL,
  `grado_destino` varchar(50) DEFAULT NULL,
  `comentario` text DEFAULT NULL,
  `estado` varchar(20) DEFAULT 'PENDIENTE',
  `respuesta_admin` text DEFAULT NULL,
  `fecha_solicitud` datetime DEFAULT current_timestamp(),
  PRIMARY KEY (`id_solicitud_matricula`),
  KEY `id_alumno` (`id_alumno`),
  CONSTRAINT `solicitud_matricula_ibfk_1` FOREIGN KEY (`id_alumno`) REFERENCES `alumno` (`id_alumno`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `solicitud_matricula`
--

LOCK TABLES `solicitud_matricula` WRITE;
/*!40000 ALTER TABLE `solicitud_matricula` DISABLE KEYS */;
/*!40000 ALTER TABLE `solicitud_matricula` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `solicitud_tramite`
--

DROP TABLE IF EXISTS `solicitud_tramite`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `solicitud_tramite` (
  `id_solicitud_tramite` int(11) NOT NULL AUTO_INCREMENT,
  `id_alumno` int(11) DEFAULT NULL,
  `id_tipo_tramite` int(11) DEFAULT NULL,
  `fecha_solicitud` datetime DEFAULT current_timestamp(),
  `estado` varchar(20) DEFAULT 'PENDIENTE_PAGO',
  `archivo_adjunto` varchar(255) DEFAULT NULL,
  `comentario_usuario` text DEFAULT NULL,
  `respuesta_administrativa` text DEFAULT NULL,
  PRIMARY KEY (`id_solicitud_tramite`),
  KEY `id_alumno` (`id_alumno`),
  KEY `id_tipo_tramite` (`id_tipo_tramite`),
  CONSTRAINT `solicitud_tramite_ibfk_1` FOREIGN KEY (`id_alumno`) REFERENCES `alumno` (`id_alumno`),
  CONSTRAINT `solicitud_tramite_ibfk_2` FOREIGN KEY (`id_tipo_tramite`) REFERENCES `tipo_tramite` (`id_tipo_tramite`)
) ENGINE=InnoDB AUTO_INCREMENT=10 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `solicitud_tramite`
--

LOCK TABLES `solicitud_tramite` WRITE;
/*!40000 ALTER TABLE `solicitud_tramite` DISABLE KEYS */;
INSERT INTO `solicitud_tramite` VALUES (8,538,6,'2026-05-24 23:54:07','PAGADO_PENDIENTE_REV',NULL,'solicito mi inasistencia',NULL),(9,538,6,'2026-07-27 23:22:59','PENDIENTE_PAGO',NULL,NULL,NULL);
/*!40000 ALTER TABLE `solicitud_tramite` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `solicitud_verano`
--

DROP TABLE IF EXISTS `solicitud_verano`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `solicitud_verano` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `id_alumno` int(11) NOT NULL,
  `id_anio_escolar` varchar(6) DEFAULT NULL,
  `id_grado` int(11) DEFAULT NULL,
  `origen` varchar(20) DEFAULT NULL,
  `modalidad` varchar(20) DEFAULT NULL,
  `estado` varchar(20) DEFAULT 'PENDIENTE_PAGO',
  `id_pago` int(11) DEFAULT NULL,
  `id_matricula` int(11) DEFAULT NULL,
  `fecha` datetime DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_sv_alumno` (`id_alumno`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `solicitud_verano`
--

LOCK TABLES `solicitud_verano` WRITE;
/*!40000 ALTER TABLE `solicitud_verano` DISABLE KEYS */;
/*!40000 ALTER TABLE `solicitud_verano` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `solicitud_verano_curso`
--

DROP TABLE IF EXISTS `solicitud_verano_curso`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `solicitud_verano_curso` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `id_solicitud_verano` int(11) NOT NULL,
  `id_curso` int(11) NOT NULL,
  `es_taller` tinyint(1) NOT NULL DEFAULT 0,
  PRIMARY KEY (`id`),
  KEY `idx_svc_solicitud` (`id_solicitud_verano`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `solicitud_verano_curso`
--

LOCK TABLES `solicitud_verano_curso` WRITE;
/*!40000 ALTER TABLE `solicitud_verano_curso` DISABLE KEYS */;
/*!40000 ALTER TABLE `solicitud_verano_curso` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `tarea`
--

DROP TABLE IF EXISTS `tarea`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `tarea` (
  `id_tarea` int(11) NOT NULL AUTO_INCREMENT,
  `id_carga_academica` int(11) DEFAULT NULL,
  `titulo` varchar(150) NOT NULL,
  `descripcion` text DEFAULT NULL,
  `fecha_publicacion` datetime DEFAULT current_timestamp(),
  `fecha_entrega` datetime DEFAULT NULL,
  `estado` varchar(20) DEFAULT 'ACTIVO',
  `tipo_evaluacion` enum('TAREA','EXAMEN_PARCIAL','EXAMEN_BIMESTRAL') NOT NULL DEFAULT 'TAREA',
  `bimestre` int(11) NOT NULL COMMENT '1 al 4',
  `peso` int(11) DEFAULT 0,
  `archivo_adjunto_url` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id_tarea`),
  KEY `id_carga_academica` (`id_carga_academica`),
  CONSTRAINT `tarea_ibfk_1` FOREIGN KEY (`id_carga_academica`) REFERENCES `carga_academica` (`id_carga_academica`)
) ENGINE=InnoDB AUTO_INCREMENT=9 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `tarea`
--

LOCK TABLES `tarea` WRITE;
/*!40000 ALTER TABLE `tarea` DISABLE KEYS */;
INSERT INTO `tarea` VALUES (8,10,'Tarea sobre la célula',NULL,'2026-06-18 09:11:07','2026-07-01 15:30:00','ACTIVO','TAREA',1,20,'/media/recursos_tareas/carga_10/ref_319a77.pdf');
/*!40000 ALTER TABLE `tarea` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `tipo_falta`
--

DROP TABLE IF EXISTS `tipo_falta`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `tipo_falta` (
  `id_tipo_falta` int(11) NOT NULL AUTO_INCREMENT,
  `nombre` varchar(60) NOT NULL,
  PRIMARY KEY (`id_tipo_falta`),
  UNIQUE KEY `nombre` (`nombre`)
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `tipo_falta`
--

LOCK TABLES `tipo_falta` WRITE;
/*!40000 ALTER TABLE `tipo_falta` DISABLE KEYS */;
INSERT INTO `tipo_falta` VALUES (1,'Asistencia y Puntualidad'),(3,'Civismo, Solidaridad y Ayuda Mutua'),(2,'Conservación del Mobiliario e Infraestructura'),(4,'Honradez'),(5,'Respeto');
/*!40000 ALTER TABLE `tipo_falta` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `tipo_pago`
--

DROP TABLE IF EXISTS `tipo_pago`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `tipo_pago` (
  `id_tipo_pago` int(11) NOT NULL AUTO_INCREMENT,
  `nombre` varchar(150) NOT NULL,
  `categoria` enum('VACANTE','MATRICULA','PENSION','MODULO','OTRO') DEFAULT 'OTRO',
  `costo` decimal(10,2) NOT NULL,
  `fecha_inicio` varchar(5) NOT NULL,
  `fecha_vencimiento` varchar(5) NOT NULL,
  `mora` decimal(10,2) DEFAULT 0.00,
  `accion_vencimiento` enum('DESHABILITAR','APLICAR_MORA') DEFAULT 'APLICAR_MORA',
  `activo` tinyint(1) DEFAULT 1,
  `periodo_academico` enum('REGULAR','VERANO','AMBOS') NOT NULL DEFAULT 'REGULAR',
  PRIMARY KEY (`id_tipo_pago`)
) ENGINE=InnoDB AUTO_INCREMENT=14 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `tipo_pago`
--

LOCK TABLES `tipo_pago` WRITE;
/*!40000 ALTER TABLE `tipo_pago` DISABLE KEYS */;
INSERT INTO `tipo_pago` VALUES (9,'Vacante','VACANTE',100.00,'01-01','10-10',0.00,'DESHABILITAR',1,'REGULAR'),(10,'Matricula','MATRICULA',200.00,'01-01','10-10',0.00,'DESHABILITAR',1,'REGULAR'),(11,'Pensión regular','PENSION',250.00,'01-01','01-30',5.00,'APLICAR_MORA',1,'REGULAR'),(12,'Modulo 1','MODULO',150.00,'03-09','03-30',5.00,'APLICAR_MORA',1,'REGULAR'),(13,'Modulo 2','MODULO',150.00,'03-09','07-30',5.00,'APLICAR_MORA',1,'REGULAR');
/*!40000 ALTER TABLE `tipo_pago` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `tipo_tramite`
--

DROP TABLE IF EXISTS `tipo_tramite`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `tipo_tramite` (
  `id_tipo_tramite` int(11) NOT NULL AUTO_INCREMENT,
  `nombre` varchar(100) NOT NULL,
  `costo` decimal(10,2) DEFAULT 0.00,
  `requisitos` text DEFAULT NULL,
  `activo` tinyint(1) DEFAULT 1,
  `alcance` varchar(20) DEFAULT 'TODOS',
  `periodo_academico` enum('REGULAR','VERANO','AMBOS') DEFAULT 'REGULAR',
  `grados_permitidos` varchar(255) DEFAULT NULL,
  `dias_vencimiento` int(11) NOT NULL DEFAULT 15,
  PRIMARY KEY (`id_tipo_tramite`)
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `tipo_tramite`
--

LOCK TABLES `tipo_tramite` WRITE;
/*!40000 ALTER TABLE `tipo_tramite` DISABLE KEYS */;
INSERT INTO `tipo_tramite` VALUES (6,'Justificación de inasistencia',10.00,'Adjuntar receta medica o ticket de atención.',1,'TODOS','AMBOS',NULL,2);
/*!40000 ALTER TABLE `tipo_tramite` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `tutor_seccion`
--

DROP TABLE IF EXISTS `tutor_seccion`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `tutor_seccion` (
  `id_tutor_seccion` int(11) NOT NULL AUTO_INCREMENT,
  `id_anio_escolar` char(6) NOT NULL,
  `id_seccion` int(11) NOT NULL,
  `id_docente` int(11) NOT NULL,
  PRIMARY KEY (`id_tutor_seccion`),
  KEY `id_anio_escolar` (`id_anio_escolar`),
  KEY `id_seccion` (`id_seccion`),
  KEY `id_docente` (`id_docente`),
  CONSTRAINT `tutor_seccion_ibfk_1` FOREIGN KEY (`id_anio_escolar`) REFERENCES `anio_escolar` (`id_anio_escolar`),
  CONSTRAINT `tutor_seccion_ibfk_2` FOREIGN KEY (`id_seccion`) REFERENCES `seccion` (`id_seccion`),
  CONSTRAINT `tutor_seccion_ibfk_3` FOREIGN KEY (`id_docente`) REFERENCES `docente` (`id_docente`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `tutor_seccion`
--

LOCK TABLES `tutor_seccion` WRITE;
/*!40000 ALTER TABLE `tutor_seccion` DISABLE KEYS */;
INSERT INTO `tutor_seccion` VALUES (1,'2026',9,3),(2,'2026',10,4),(3,'2026',7,3);
/*!40000 ALTER TABLE `tutor_seccion` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `usuario`
--

DROP TABLE IF EXISTS `usuario`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `usuario` (
  `id_usuario` int(11) NOT NULL AUTO_INCREMENT,
  `username` varchar(50) NOT NULL,
  `password_hash` varchar(255) NOT NULL,
  `rol` enum('ADMIN','DOCENTE','ALUMNO','AUXILIAR','PSICOLOGO') NOT NULL,
  `activo` tinyint(1) DEFAULT 1,
  `fecha_creacion` datetime DEFAULT current_timestamp(),
  PRIMARY KEY (`id_usuario`),
  UNIQUE KEY `username` (`username`)
) ENGINE=InnoDB AUTO_INCREMENT=43 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `usuario`
--

LOCK TABLES `usuario` WRITE;
/*!40000 ALTER TABLE `usuario` DISABLE KEYS */;
INSERT INTO `usuario` VALUES (24,'81246124','$2b$12$DnruF/Rw1ml2vsn466GnaOn9UOPtI2HyR.8P7n7SrbIDI0ghLD4i2','ADMIN',1,'2026-03-21 15:12:32'),(32,'72640066','$2b$12$/k8jDgd72dljzdU.E/XenOLZlRAwj7c6R7IzYqCUhPSZnFu//fsxO','DOCENTE',1,'2026-04-30 21:45:07'),(33,'12131415','$2b$12$RKW6rlTU/Zx38MtFAWrB4uciQ3mZtMOql/Xbqd9wy2X2K4HCbc/k.','AUXILIAR',1,'2026-04-30 21:45:52'),(37,'12345678','$2b$12$q/9wN5ZnfbLUeRWUgL0VG.1.PLoAPx/Wfnps6PfyHDmnOmOIw.Kzi','ALUMNO',1,'2026-05-23 01:24:49'),(38,'10000001','$2b$12$RqEdQGT0rrltUSk1t0sD2OKo0RsP6oLx/LtktbMVOCRjArTmp5mLS','ALUMNO',1,'2026-05-23 22:42:02'),(39,'10000002','$2b$12$RqEdQGT0rrltUSk1t0sD2OKo0RsP6oLx/LtktbMVOCRjArTmp5mLS','ALUMNO',1,'2026-05-23 22:42:02'),(40,'10000003','$2b$12$RqEdQGT0rrltUSk1t0sD2OKo0RsP6oLx/LtktbMVOCRjArTmp5mLS','ALUMNO',1,'2026-05-23 22:42:02'),(41,'70111222','$2b$12$RqEdQGT0rrltUSk1t0sD2OKo0RsP6oLx/LtktbMVOCRjArTmp5mLS','DOCENTE',1,'2026-05-23 22:53:09'),(42,'60415217','$2b$12$oaWhFSYW4tWkolozZizAQuVzniA6ZyP.AyOvV.LnAj6c.8vWSRlNC','PSICOLOGO',1,'2026-06-19 19:42:39');
/*!40000 ALTER TABLE `usuario` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Dumping events for database 'segunda_amancio_bd'
--

--
-- Dumping routines for database 'segunda_amancio_bd'
--
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-08-03 11:52:01
