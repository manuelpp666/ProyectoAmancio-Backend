-- Respaldo previo a corregir DNI de personal, 2026-08-07 18:32:35
-- Ejecutar este archivo revierte la corrección.

UPDATE `alumno` SET `dni` = '99999901' WHERE `id_alumno` = 1;
UPDATE `usuario` SET `username` = 'ALU-99999901' WHERE `id_usuario` = 49;
