-- Respaldo previo a corregir DNI de personal, 2026-08-07 18:28:59
-- Ejecutar este archivo revierte la corrección.

UPDATE `administrador` SET `dni` = '99999901' WHERE `id_admin` = 1;
UPDATE `usuario` SET `username` = 'ADM-99999901' WHERE `id_usuario` = 1;
UPDATE `psicologo` SET `dni` = '99999901' WHERE `id_psicologo` = 1;
UPDATE `usuario` SET `username` = 'PSI-99999901' WHERE `id_usuario` = 6;
UPDATE `auxiliar` SET `dni` = '99999901' WHERE `id_auxiliar` = 1;
UPDATE `usuario` SET `username` = 'AUX-99999901' WHERE `id_usuario` = 7;
UPDATE `docente` SET `dni` = '99999901' WHERE `id_docente` = 1;
UPDATE `usuario` SET `username` = 'DOC-99999901' WHERE `id_usuario` = 12;
