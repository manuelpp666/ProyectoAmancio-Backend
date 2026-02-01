import bcrypt

def get_password_hash(password: str) -> str:
    # Convertimos la cadena a bytes
    pwd_bytes = password.encode('utf-8')
    # Generamos el salt y el hash
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(pwd_bytes, salt)
    # Devolvemos como string para guardar en la BD
    return hashed_password.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    # Comparamos convirtiendo ambos a bytes
    return bcrypt.checkpw(
        plain_password.encode('utf-8'), 
        hashed_password.encode('utf-8')
    )