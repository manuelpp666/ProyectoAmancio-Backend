import os
import time
from dotenv import load_dotenv
from google import genai

# Cargar variables de entorno (.env)
load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

if not GOOGLE_API_KEY:
    print("❌ Error: No se encontró la variable GOOGLE_API_KEY en el archivo .env")
    exit(1)

client = genai.Client(api_key=GOOGLE_API_KEY)

print("🔍 Obteniendo lista de modelos disponibles para tu API Key...\n")

try:
    # 1. Obtener todos los modelos asignados a tu API Key
    all_models = client.models.list()
    
    # 2. Filtrar solo los modelos que soportan generación de contenido
    candidate_models = []
    for m in all_models:
        # Extraer el nombre limpio (ej. "gemini-2.5-flash" en lugar de "models/gemini-2.5-flash")
        model_name = m.name.replace("models/", "")
        
        # Filtramos para probar modelos de texto/chat de la familia gemini
        if "gemini" in model_name and "embed" not in model_name and "imagen" not in model_name:
            candidate_models.append(model_name)

    # Eliminar duplicados manteniendo orden
    candidate_models = list(dict.fromkeys(candidate_models))

except Exception as e:
    print(f"❌ Error al consultar la lista de modelos: {e}")
    exit(1)

if not candidate_models:
    print("⚠️ No se encontraron modelos compatibles con generación de texto.")
    exit(0)

print(f"📋 Se encontraron {len(candidate_models)} candidatos de texto. Evaluando velocidad...\n")
print("-" * 65)
print(f"{'MODELO':<35} | {'ESTADO':<10} | {'TIEMPO (s)':<10}")
print("-" * 65)

results = []
test_prompt = "Responde únicamente con la palabra 'OK'."

# 3. Probar la latencia de cada modelo
for model_name in candidate_models:
    t0 = time.perf_counter()
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=test_prompt
        )
        elapsed = time.perf_counter() - t0
        results.append({
            "model": model_name,
            "status": "ÉXITO",
            "time": elapsed
        })
        print(f"{model_name:<35} | {'✅ ÉXITO':<10} | {elapsed:.3f} s")
    except Exception as e:
        elapsed = time.perf_counter() - t0
        # Muestra un resumen del error si el modelo no está disponible
        err_msg = str(e)
        short_err = "404 NOT_FOUND" if "404" in err_msg else "FALLÓ"
        results.append({
            "model": model_name,
            "status": short_err,
            "time": float('inf')
        })
        print(f"{model_name:<35} | {f'❌ {short_err}':<10} | N/A")

print("-" * 65)
print("\n🏆 RANKING DE MODELOS MÁS RÁPIDOS (Funcionales):\n")

# 4. Filtrar exitosos y ordenar por tiempo de respuesta
successful_models = [r for r in results if r["status"] == "ÉXITO"]
successful_models.sort(key=lambda x: x["time"])

if successful_models:
    for rank, item in enumerate(successful_models, 1):
        print(f"{rank}. {item['model']:<30} ➔ {item['time']:.3f} segundos")
        
    print(f"\n💡 Sugerencia para tu backend:")
    print(f"   PRIMARY_MODEL  = \"{successful_models[0]['model']}\"")
    if len(successful_models) > 1:
        print(f"   FALLBACK_MODEL = \"{successful_models[1]['model']}\"")
else:
    print("❌ Ningún modelo respondió con éxito. Revisa tu API Key o cuota disponible.")