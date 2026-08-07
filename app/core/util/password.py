"""
Hasheo de contraseñas.

bcrypt es lento a propósito: es lo que hace inviable probar millones de claves
si algún día se filtra la tabla de usuarios. El precio es que ese coste también
lo paga el servidor en cada inicio de sesión.

Medido en el equipo de desarrollo, con el coste 12 que trae bcrypt por defecto,
verificar una contraseña tarda unos 155 ms. Eso es un núcleo ocupado durante
155 ms por cada login, o sea unos 6 logins por segundo y núcleo. Para el
colegio entero (577 alumnos entrando a lo largo de la mañana) sobra, pero es el
punto más ajustado de la aplicación, así que el coste se deja configurable:

    BCRYPT_ROUNDS=11   # ~2x más rápido que 12
    BCRYPT_ROUNDS=10   # ~4x más rápido; es el mínimo que recomienda OWASP

No bajar de 10. Y ojo: el coste va grabado dentro de cada hash, así que
cambiarlo solo afecta a las contraseñas que se creen o se cambien a partir de
entonces; las ya guardadas se siguen verificando con el coste con el que
nacieron.
"""
import os

import bcrypt

_MINIMO = 10
_POR_DEFECTO = 12


def _rondas() -> int:
    try:
        valor = int((os.getenv("BCRYPT_ROUNDS") or "").strip() or _POR_DEFECTO)
    except ValueError:
        return _POR_DEFECTO
    return max(_MINIMO, min(valor, 16))


RONDAS = _rondas()


def get_password_hash(password: str) -> str:
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt(rounds=RONDAS)
    hashed_password = bcrypt.hashpw(pwd_bytes, salt)
    return hashed_password.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    # Un hash corrupto o vacío en la base no debe tumbar el login con una
    # excepción: es simplemente una contraseña que no coincide.
    try:
        return bcrypt.checkpw(
            plain_password.encode('utf-8'),
            hashed_password.encode('utf-8')
        )
    except (ValueError, TypeError):
        return False
