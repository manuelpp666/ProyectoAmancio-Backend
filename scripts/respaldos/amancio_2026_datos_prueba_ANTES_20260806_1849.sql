-- Datos de prueba borrados de amancio_2026 el 2026-08-06 18:49
-- Volcar este archivo restaura exactamente lo eliminado.

INSERT INTO `usuario` (`id_usuario`, `username`, `password_hash`, `rol`, `activo`, `debe_cambiar_password`, `fecha_creacion`) VALUES (631, 'ADM-99990001', '$2b$12$K/IT5SMDmnYrFgArbVFzKeom8l4IFXWpzNrQex8pGIkibrfYW/89m', 'ADMIN', 1, 0, '2026-08-06 18:30:06');
INSERT INTO `administrador` (`id_admin`, `id_usuario`, `dni`, `nombres`, `apellidos`, `telefono`, `email`, `url_perfil`, `permisos`) VALUES (7, 631, '99990001', 'Cuenta', 'Temporal Prueba', NULL, 'temporal@example.com', NULL, NULL);
INSERT INTO `mensaje` (`id_mensaje`, `id_conversacion`, `remitente_id`, `contenido`, `leido`, `fecha_envio`) VALUES (1, 2, 6, 'hola', 0, '2026-08-06 18:32:41');
INSERT INTO `conversacion` (`id_conversacion`, `usuario1_id`, `usuario2_id`, `ultimo_mensaje`, `fecha_actualizacion`) VALUES (1, 5, 1, NULL, '2026-08-06 17:27:43');
INSERT INTO `conversacion` (`id_conversacion`, `usuario1_id`, `usuario2_id`, `ultimo_mensaje`, `fecha_actualizacion`) VALUES (2, 6, 47, 'hola', '2026-08-06 18:32:41');
