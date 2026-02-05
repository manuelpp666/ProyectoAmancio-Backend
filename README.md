-- Idea base
app/
├── core/                # Seguridad (JWT), config de entorno, constantes.
├── db/                  # Conexión a DB y base de los modelos.
├── modules/             # Aquí vive la lógica del colegio dividida por contexto
│   ├── auth/            # Login, registro de profes/alumnos
│   ├── enrollment/      # Gestión de matrículas
│   │   ├── router.py
│   │   ├── schemas.py
│   │   ├── service.py   # Lógica: "¿El alumno debe documentos?"
│   │   └── models.py
│   ├── payments/        # Pasarelas de pago, facturas, deudas
│   │   ├── router.py
│   │   ├── service.py   # Lógica: "Validar transacción con banco"
│   │   └── models.py
│   └── campus/          # Material de clases, tareas, notas
└── main.py              # Registro de todos los módulos

-- Estructura v1.0
app/
└── modules/
    ├── users/               <-- YA EXISTE (Expandir)
    │   ├── usuario/         (Manejo de login y usuarios base)
    │   ├── docente/         (Ya lo tienes)
    │   ├── alumno/          (Nuevo)
    │   └── familiar/        (Nuevo)
    ├── academic/            <-- NUEVO (Todo lo académico: Grados, Cursos, Secciones)
    ├── enrollment/          <-- NUEVO (Matrícula y Exoneraciones)
    ├── finance/             <-- NUEVO (Pagos y Trámites)
    ├── management/          <-- NUEVO (Notas, Asistencia, Carga Académica)
    ├── behavior/            <-- NUEVO (Conducta y Psicología)
    └── web/                 <-- NUEVO (Noticias y Eventos)

--- Resumen simple de lo que hace cada parte (Hecho por Gemini)
1. El Router (router.py) - El Mesero
El router es el que recibe al cliente (el frontend). Su única misión es:

Recibir la orden (el request).

Validar que los datos básicos estén ahí (usando los Schemas).

Pasarle el pedido a la cocina y entregar la respuesta al cliente.

No cocina. Si hay un cálculo de impuestos en el pago, el mesero no lo hace.

2. El Service (service.py) - El Chef (Lógica de Negocio)
Aquí es donde ocurre la "magia" y es la parte más importante para tu colegio.

Si un alumno se matricula, el service verifica: ¿Hay cupo? ¿Pagó la reserva? ¿Tiene los documentos completos?

Es código Python puro. No sabe si los datos vienen de una web o de una app móvil; él solo ejecuta las reglas del colegio.

3. El Schema (schemas.py) - El Menú / Contrato
Son modelos de Pydantic. Definen exactamente qué datos puede enviar o recibir el usuario.

Ejemplo: Un schema de "Pago" dice que el monto debe ser un número positivo y la moneda debe ser "USD" o "PEN". Si envían texto en el precio, FastAPI lo rebota automáticamente.

4. El Model (models.py) - La Alacena (Base de Datos)
Es la representación de tus tablas en la base de datos (usando SQLAlchemy).

Define que la tabla alumnos tiene una columna id, nombre y correo.


--- Instalación----
1. pip install fastapi "uvicorn[standard]" sqlalchemy pymysql cryptography alembic python-dotenv pydantic-settings python-multipart

pip install "pydantic[email]"

pip install "passlib[bcrypt]"

1.
pip install -U python-multipart google-genai langchain langchain-pinecone pinecone-client pypdf langchain-huggingface sentence-transformers

2. pip install langchain-community


3. pip install python-docx

4. pip install docx2txt
