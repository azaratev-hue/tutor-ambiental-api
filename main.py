# -*- coding: utf-8 -*-
"""
Created on Sun Mar 22 15:28:58 2026

@author: azara
"""
from fastapi import FastAPI
from pydantic import BaseModel
from tutor_v06 import graph
from dotenv import load_dotenv
from neo4j_client import Neo4jClient

load_dotenv()

neo4j_client = Neo4jClient()

app = FastAPI()


class Pregunta(BaseModel):
    pregunta: str
    usuario_id: str


@app.get("/")
def home():
    return {"mensaje": "Tutor IA activo"}


@app.post("/preguntar")
def preguntar(data: Pregunta):

    # ===============================
    # 1. INVOCAR MODELO
    # ===============================
    result = graph.invoke({
        "pregunta": data.pregunta,
        "usuario_id": data.usuario_id
    })

    # ===============================
    # 2. EXTRAER CONCEPTOS
    # ===============================
    conceptos = result.get("conceptos", [])

    # ===============================
    # 3. GUARDAR EN NEO4J
    # ===============================
    if conceptos:
        neo4j_client.guardar_aprendizaje(data.usuario_id, conceptos)

    # ===============================
    # 4. ACTUALIZAR NIVEL
    # ===============================
    nivel_info = neo4j_client.actualizar_nivel_usuario(data.usuario_id)

    # ===============================
    # 5. RESPUESTA FINAL
    # ===============================
    return {
        "respuesta": result.get("respuesta"),
        "nivel_detectado_llm": result.get("nivel"),
        "nivel_usuario": nivel_info["nivel"],
        "conceptos_aprendidos_total": nivel_info["total_conceptos"],
        "conceptos": conceptos,
        "recomendaciones": result.get("recomendaciones")
    }
