# -*- coding: utf-8 -*-
"""
Created on Sun Mar 22 15:28:58 2026

@author: azara
"""

from fastapi import FastAPI
from pydantic import BaseModel
from tutor_v06 import graph
#import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()


class Pregunta(BaseModel):
    pregunta: str
    usuario_id: str


@app.get("/")
def home():
    return {"mensaje": "Tutor IA activo"}


@app.post("/preguntar")
def preguntar(data: Pregunta):

    result = graph.invoke({
        "pregunta": data.pregunta,
        "usuario_id": data.usuario_id
    })

    # 🔥 EXTRAER conceptos del resultado
    conceptos = result.get("conceptos", [])

    # 🔥 GUARDAR EN NEO4J
    if conceptos:
        neo4j_client.guardar_aprendizaje(data.usuario_id, conceptos)

    return {
        "respuesta": result.get("respuesta"),
        "nivel": result.get("nivel"),
        "conceptos": conceptos,
        "recomendaciones": result.get("recomendaciones")
    }
