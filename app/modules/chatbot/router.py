import os
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_pinecone import PineconeVectorStore
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from docx import Document as DocxDocument
from langchain_core.documents import Document as LangDocument
from typing import List
from datetime import datetime
from docx.table import Table
from docx.text.paragraph import Paragraph
import os
import uuid
import shutil
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.db.database import get_db
from .models import Chatbot
from .schemas import ChatbotResponse
from app.core.util.security import get_current_user


load_dotenv()

FILE_DIR = os.path.dirname(os.path.abspath(__file__))

# 2. Subimos 3 niveles: virtual -> modules -> app -> Backend
# Esto garantiza que BASE_DIR sea la carpeta raíz del proyecto Backend
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(FILE_DIR)))
UPLOAD_DIR = os.path.join(BASE_DIR, "media", "chatbot_files")
os.makedirs(UPLOAD_DIR, exist_ok=True)

MAX_FILE_SIZE_MB = 10
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc"}
MAX_DOCUMENTS = 5

# Namespace fijo: TODOS los documentos del colegio viven en el mismo namespace.
# Esto evita inconsistencias entre upload / ask / delete.
NAMESPACE = "colegio"

# Configuracion
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
INDEX_NAME = os.getenv("INDEX_NAME", "colegio-knowledge")

# Aplicar al entorno para que LangChain lo detecte automáticamente
os.environ["PINECONE_API_KEY"] = PINECONE_API_KEY

router = APIRouter(prefix="/chatbot", tags=["Chatbot"])

# IMPORTANTE: tu índice de Pinecone tiene Dimension: 3072.
# El modelo de embeddings DEBE producir vectores de 3072 dimensiones o
# Pinecone rechazará el upsert (o lo truncará/fallará silenciosamente
# según el cliente). "models/gemini-embedding-2" -> revisa que efectivamente
# devuelva 3072 dims; si tu plan/SDK lo soporta con output_dimensionality,
# fíjalo explícitamente para que coincida siempre con el índice.
embeddings = GoogleGenerativeAIEmbeddings(
    model="models/gemini-embedding-2",
    google_api_key=GOOGLE_API_KEY
)

client = genai.Client(api_key=GOOGLE_API_KEY)

# Vectorstore reutilizable (evita crear conexiones nuevas en cada request)
vectorstore = PineconeVectorStore(
    index_name=INDEX_NAME,
    embedding=embeddings,
    namespace=NAMESPACE
)

# --- ENDPOINTS DE CONSULTA Y GESTIÓN ---

@router.get("/documents", response_model=List[ChatbotResponse])
def get_documents(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes ver esta información")
    return db.query(Chatbot).all()


@router.get("/download/{doc_id}")
def download_document(doc_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes ver esta información")
    doc = db.query(Chatbot).filter(Chatbot.id == doc_id).first()
    if not doc or not os.path.exists(doc.file_path):
        raise HTTPException(status_code=404, detail="Archivo no encontrado.")
    return FileResponse(path=doc.file_path, filename=doc.filename)


@router.delete("/delete/{doc_id}")
def delete_document(doc_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes ver esta información")
    
    doc = db.query(Chatbot).filter(Chatbot.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado.")

    # 1. INTENTO DE BORRADO EN PINECONE (Independiente)
    try:
        if doc.total_chunks and doc.total_chunks > 0:
            # ¡LA SOLUCIÓN! Limpiamos el nombre exactamente igual que en el upload
            safe_filename = doc.filename.replace(" ", "_")
            ids_to_delete = [f"{safe_filename}-{i}" for i in range(doc.total_chunks)]
            
            vectorstore.delete(ids=ids_to_delete, namespace=NAMESPACE)
            print(f"[PINECONE] Se eliminaron {len(ids_to_delete)} chunks correctamente.")
    except Exception as e:
        # Si da error, imprimimos la advertencia pero NO detenemos el proceso.
        print(f"[PINECONE WARNING] No se pudo borrar de Pinecone o ya no existe: {str(e)}")

    # 2. BORRADO LOCAL Y SQL (Aislado de fallos de Pinecone)
    try:
        # ELIMINAR ARCHIVO FÍSICO
        if doc.file_path and os.path.exists(doc.file_path):
            os.remove(doc.file_path)

        # ELIMINAR DE SQL
        db.delete(doc)
        db.commit()

        return {"message": f"'{doc.filename}' Eliminado correctamente del sistema."}

    except Exception as e:
        print(f"[ERROR LOCAL en /delete] {str(e)}") 
        raise HTTPException(
            status_code=500,
            detail=f"Error al eliminar los archivos locales o la base de datos: {str(e)}"
        )
# --- ENDPOINT DE SUBIDA Y ENTRENAMIENTO ---

@router.post("/upload")
async def upload(file: UploadFile = File(...), db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "ADMIN":
        raise HTTPException(status_code=403, detail="No puedes ver esta información")

    # 1. Validación de cantidad
    count = db.query(Chatbot).count()
    if count >= MAX_DOCUMENTS:
        raise HTTPException(status_code=400, detail=f"Límite de {MAX_DOCUMENTS} archivos alcanzado.")

    # 1.b Evitar duplicados: si ya existe un documento con el mismo nombre,
    # lo rechazamos (o podrías optar por sobrescribir, ver nota abajo).
    existing = db.query(Chatbot).filter(Chatbot.filename == file.filename).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Ya existe un documento llamado '{file.filename}'. Elimínalo primero si quieres reemplazarlo."
        )

    # 2. Validación de extensión
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Formato no soportado. Usa PDF o DOCX.")

    # 3. Validación de peso (Backend)
    content = await file.read()
    file_size = len(content)

    if file_size > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"El archivo excede el límite de {MAX_FILE_SIZE_MB}MB."
        )

    if file_size == 0:
        raise HTTPException(status_code=400, detail="El archivo está vacío.")

    unique_name = f"{uuid.uuid4().hex[:8]}_{file.filename}"
    temp_path = os.path.join(UPLOAD_DIR, unique_name)
    try:
        # 1. Guardar el archivo físicamente para que docx/PyPDFLoader puedan leerlo
        with open(temp_path, "wb") as f:
            f.write(content)

        full_content = []

        if file.filename.lower().endswith((".docx", ".doc")):
            doc_file = DocxDocument(temp_path)

            # 2. Extracción secuencial (Párrafos y Tablas en orden)
            for element in doc_file.element.body:
                if element.tag.endswith('}p'):
                    para = Paragraph(element, doc_file)
                    if para.text.strip():
                        full_content.append(para.text)

                elif element.tag.endswith('}tbl'):
                    table = Table(element, doc_file)
                    table_rows = []
                    for row in table.rows:
                        cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                        table_rows.append(f"| {' | '.join(cells)} |")

                    tabla_texto = "\n[TABLA DETECTADA]\n" + "\n".join(table_rows) + "\n"
                    full_content.append(tabla_texto)

            text_to_process = "\n\n".join(full_content)

        elif file.filename.lower().endswith(".pdf"):
            loader = PyPDFLoader(temp_path)
            pdf_docs = loader.load()
            text_to_process = "\n\n".join([d.page_content for d in pdf_docs])
        else:
            os.remove(temp_path)
            return {"message": "Formato no soportado."}

        if not text_to_process.strip():
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise HTTPException(status_code=400, detail="El archivo no contiene texto legible (puede que sea una imagen o esté protegido).")

        # 3. Creación de Documento de LangChain
        doc_obj = LangDocument(page_content=text_to_process, metadata={"source": file.filename})

        # 4. Chunking Estratégico (Reducimos un poco el tamaño para asegurar compatibilidad)
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000, 
            chunk_overlap=200,
            separators=["\n\n", "\n", ". ", " ", ""]
        )
        final_docs = text_splitter.split_documents([doc_obj])

        if not final_docs:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return {"message": "No se extrajo contenido del archivo."}

        # Limpiamos el nombre del archivo para que los IDs no tengan espacios (evita bugs raros)
        safe_filename = file.filename.replace(" ", "_")
        ids = [f"{safe_filename}-{i}" for i in range(len(final_docs))]

        # 5. SUBIDA UNO POR UNO (Solución al bug de truncamiento silencioso)
        upserted_count = 0

        print(f"Iniciando subida de {len(final_docs)} chunks (uno por uno)...")

        for i, doc in enumerate(final_docs):
            try:
                # Enviamos el documento individualmente asegurando que el embedding coincida 1 a 1
                res_ids = vectorstore.add_documents(
                    documents=[doc],
                    ids=[ids[i]],
                    namespace=NAMESPACE,
                    async_req=False
                )
                if res_ids:
                    upserted_count += len(res_ids)
                    print(f"[PINECONE] Chunk subido correctamente: {res_ids}")
            except Exception as chunk_error:
                print(f"[ERROR Chunk {i}] {str(chunk_error)}")
                raise HTTPException(
                    status_code=500, 
                    detail=f"La API de IA falló en el fragmento {i}. Error: {str(chunk_error)}"
                )

        print(f"[PINECONE] Subida completada. Total insertados: {upserted_count} de {len(final_docs)}")

        # 5.b VERIFICACIÓN REAL GLOBAL
        try:
            stats = vectorstore.index.describe_index_stats()
            namespace_stats = stats.get("namespaces", {}).get(NAMESPACE, {})
            vectores_totales = namespace_stats.get("vector_count", 0)
        except Exception as e:
            vectores_totales = None
            print(f"[PINECONE] No se pudo verificar el conteo total: {e}")

        # Guardamos en BD
        clean_ext = file_ext.replace(".", "")
        new_record = Chatbot(
            filename=file.filename,
            unique_filename=unique_name,
            file_path=temp_path,
            file_type=clean_ext,
            pinecone_index=INDEX_NAME,
            total_chunks=upserted_count,  # Guardamos el total real que logró subir
            status="entrenado"
        )
        db.add(new_record)
        db.commit()
        
        return {
            "message": f"'{file.filename}' indexado correctamente.",
            "chunks_generados": len(final_docs),
            "chunks_confirmados_pinecone": upserted_count,
        }

    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        print(f"ERROR REAL: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- ENDPOINT DE PREGUNTA (RAG) ---

@router.post("/ask")
async def ask(question: str = Form(...)):
    hoy = datetime.now().strftime("%d de %B de %Y")
    # --- BÚSQUEDA PROFUNDA (k=20), mismo namespace que en upload/delete ---
    docs = vectorstore.similarity_search(question, k=20, namespace=NAMESPACE)

    print(f"[PINECONE] Pregunta: '{question}' -> se recuperaron {len(docs)} chunks del namespace '{NAMESPACE}'.")
    if not docs:
        print("[PINECONE][ALERTA] No se recuperó NINGÚN chunk. Revisa que el namespace "
              "y la dimensión del embedding coincidan con los documentos indexados.")

    contexto = "\n\n".join([f"FUENTE: {d.metadata.get('source')}\nCONTENIDO: {d.page_content}" for d in docs])

    prompt = f"""
    Eres el asistente informativo del colegio.
    Fecha de hoy: {hoy}

    INSTRUCCIONES DE RESPUESTA:
    1. AMBIGÜEDAD: Si el usuario pregunta por un pago pero hay varios (ej. la tabla muestra 12 meses), pregunta: "¿A qué mes o cuota te refieres? Tengo información de marzo a diciembre 📅."
    2. VALIDACIÓN: Si el usuario pregunta "qué debo pagar", compara la fecha de hoy ({hoy}) con las fechas de la tabla.
       - Si la fecha de pago ya pasó, indica que está vencido.
       - Si falta poco, recuérdale la fecha límite.
    3. TABLAS: La información de pagos está en formato | N° | PENSIÓN | FECHA |. Léela con cuidado.
    4. USA ÚNICAMENTE el contexto de abajo.
    5. Si la info no existe, di: "Lo siento, no tengo esa información precisa 🏫."

    CONTEXTO DEL REGLAMENTO:
    {contexto}

    PREGUNTA DEL USUARIO: {question}
    """

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=prompt
        )
        return {"answer": response.text}
    except Exception as e:
        # Antes este error se tragaba silenciosamente. Ahora lo imprimimos
        # en consola para poder diagnosticar la causa real (cuota excedida,
        # API key inválida, prompt demasiado largo, etc.)
        print(f"[GEMINI][ERROR REAL en /ask] {type(e).__name__}: {e}")
        return {"answer": "Error técnico, intenta de nuevo 🍎"}