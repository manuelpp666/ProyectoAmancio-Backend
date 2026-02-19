import os
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, UploadFile, File,Form, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_pinecone import PineconeVectorStore
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from docx import Document as DocxDocument  
from langchain_core.documents import Document as LangDocument
from typing import List
from datetime import datetime
from docx import Document as DocxDocument
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


# Configuracion
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
INDEX_NAME = os.getenv("INDEX_NAME", "colegio-knowledge")

# Aplicar al entorno para que LangChain lo detecte automáticamente
os.environ["PINECONE_API_KEY"] = PINECONE_API_KEY

router = APIRouter(prefix="/chatbot", tags=["Chatbot"])

embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2",
    model_kwargs={'device': 'cpu'}
)

client = genai.Client(api_key=GOOGLE_API_KEY)

# --- ENDPOINTS DE CONSULTA Y GESTIÓN ---

@router.get("/documents", response_model=List[ChatbotResponse])
def get_documents(db: Session = Depends(get_db)):
    return db.query(Chatbot).all()

@router.get("/download/{doc_id}")
def download_document(doc_id: int, db: Session = Depends(get_db)):
    doc = db.query(Chatbot).filter(Chatbot.id == doc_id).first()
    if not doc or not os.path.exists(doc.file_path):
        raise HTTPException(status_code=404, detail="Archivo no encontrado.")
    return FileResponse(path=doc.file_path, filename=doc.filename)

@router.delete("/delete/{doc_id}")
def delete_document(doc_id: int, db: Session = Depends(get_db)):
    doc = db.query(Chatbot).filter(Chatbot.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado.")
    

    try:
        # 2. ELIMINAR DE PINECONE
        # Inicializamos el acceso al vectorstore
        vectorstore = PineconeVectorStore(
            index_name=INDEX_NAME, 
            embedding=embeddings
        )
        
        # Borramos todos los vectores que tengan el metadato 'source' igual al nombre del archivo
        # Importante: Pinecone permite borrar por filtro en planes pagados. 
        # Si usas el plan gratuito (Starter), LangChain lo maneja internamente.
        vectorstore.delete(filter={"source": doc.filename})

        # 3. ELIMINAR ARCHIVO FÍSICO
        if os.path.exists(doc.file_path):
            os.remove(doc.file_path)
        
        # 4. ELIMINAR DE SQL
        db.delete(doc)
        db.commit()

        return {"message": f"'{doc.filename}' Eliminado correctamente."}

    except Exception as e:
        # Si algo falla en la conexión con Pinecone, lanzamos el error
        raise HTTPException(
            status_code=500, 
            detail=f"Error al eliminar el conocimiento: {str(e)}"
        )

# --- ENDPOINT DE SUBIDA Y ENTRENAMIENTO ---

@router.post("/upload")
async def upload(file: UploadFile = File(...), db: Session = Depends(get_db)):
    # 1. Validación de cantidad
    count = db.query(Chatbot).count()
    if count >= MAX_DOCUMENTS:
        raise HTTPException(status_code=400, detail=f"Límite de {MAX_DOCUMENTS} archivos alcanzado.")
    
    # 2. Validación de extensión (Usando la variable que definiste arriba)
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Formato no soportado. Usa PDF o DOCX.")

    # 3. Validación de peso (Backend)
    # Leemos el contenido UNA SOLA VEZ
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
        # 1. Guardar el archivo físicamente para que docx pueda leerlo
        with open(temp_path, "wb") as f:
            f.write(content)
        
        full_content = []

        if file.filename.lower().endswith((".docx", ".doc")):
            doc_file = DocxDocument(temp_path)
            
            # 2. Extracción secuencial (Párrafos y Tablas en orden)
            for element in doc_file.element.body:
                if element.tag.endswith('p'):
                    para = Paragraph(element, doc_file)
                    if para.text.strip():
                        full_content.append(para.text)
                
                elif element.tag.endswith('tbl'):
                    table = Table(element, doc_file)
                    # Formateamos la tabla como texto estructurado (Markdown-ish)
                    table_rows = []
                    for row in table.rows:
                        cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                        table_rows.append(f"| {' | '.join(cells)} |")
                    
                    # Agregamos un identificador claro para la IA
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
            if os.path.exists(temp_path): os.remove(temp_path)
            raise HTTPException(status_code=400, detail="El archivo no contiene texto legible (puede que sea una imagen o esté protegido).")

        # 3. Creación de Documentos de LangChain
        doc_obj = LangDocument(page_content=text_to_process, metadata={"source": file.filename})

        # 4. Chunking Estratégico
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1200, 
            chunk_overlap=300,
            separators=["\n\n", "\n", ". ", " ", ""]
        )
        final_docs = text_splitter.split_documents([doc_obj])

        # 5. Subida Garantizada a Pinecone
        if final_docs:
            # Forzamos la inicialización del vectorstore con los documentos
            vectorstore = PineconeVectorStore.from_documents(
                documents=final_docs,
                embedding=embeddings,
                index_name=INDEX_NAME
            )
            clean_ext = file_ext.replace(".", "")
            new_record = Chatbot(
                filename=file.filename,
                unique_filename=unique_name,
                file_path=temp_path,
                file_type=clean_ext,
                pinecone_index=INDEX_NAME,
                total_chunks=len(final_docs),
                status="entrenado"
            )
            db.add(new_record)
            db.commit()
            return {"message": f"'{file.filename}' indexado con {len(final_docs)} fragmentos."}
        else:
            if os.path.exists(temp_path): os.remove(temp_path)
            return {"message": "No se extrajo contenido del archivo."}

    except Exception as e:
        if os.path.exists(temp_path): os.remove(temp_path)
        raise HTTPException(status_code=500, detail=str(e))

# --- ENDPOINT DE PREGUNTA (RAG) ---

@router.post("/ask")
async def ask(question: str = Form(...)):
    vectorstore = PineconeVectorStore(index_name=INDEX_NAME, embedding=embeddings)
    hoy = datetime.now().strftime("%d de %B de %Y")
    # --- MEJORA 3: BÚSQUEDA PROFUNDA (k=20) ---
    docs = vectorstore.similarity_search(question, k=20)
    contexto = "\n\n".join([f"FUENTE: {d.metadata.get('source')}\nCONTENIDO: {d.page_content}" for d in docs])
    
    # --- MEJORA 4: PROMPT ULTRA-ESTRICTO ---
    prompt = f"""
    Eres el asistente informativo del colegio. 
    Fecha de hoy: {hoy}

    INSTRUCCIONES DE RESPUESTA:
    1. AMBIGÜEDAD: Si el usuario pregunta por un pago pero hay varios (ej. la tabla muestra 12 meses), pregunta: "¿A qué mes o cuota te refieres? Tengo información de marzo a diciembre 📅."
    2. VALIDACIÓN: Si el usuario pregunta "qué debo pagar", compara la fecha de hoy ({hoy}) con las fechas de la tabla. 
       - Si la fecha de pago ya pasó, indica que está vencido.
       - Si falta poco, recuérdale la fecha límite.
    3. TABLAS: La información de pagos está en formato | N° | PENSIÓN | FECHA |. Léela con cuidado.
    4.USA ÚNICAMENTE el contexto de abajo.
    5. Si la info no existe, di: "Lo siento, no tengo esa información precisa 🏫."

    CONTEXTO DEL REGLAMENTO:
    {contexto}

    PREGUNTA DEL USUARIO: {question}
    """

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite", # O usa gemini-1.5-pro si buscas máxima precisión
            contents=prompt
        )
        return {"answer": response.text}
    except Exception as e:
        return {"answer": "Error técnico, intenta de nuevo 🍎"}