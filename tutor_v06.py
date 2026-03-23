# -*- coding: utf-8 -*-
"""
Created on Sun Mar 22 13:01:07 2026

@author: azara
"""

from typing import TypedDict, List
import unicodedata
import os
from neo4j import GraphDatabase
from openai import OpenAI
from langgraph.graph import StateGraph
from dotenv import load_dotenv
load_dotenv()

# =========================================================
# CONFIG
# =========================================================

MODEL_CHAT = "gpt-5-mini"
MODEL_EMBED = "text-embedding-3-small"

TOP_K = 5
USUARIO_ID = "u001"

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

driver = GraphDatabase.driver(
    os.getenv("NEO4J_URI"),
    auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD"))
)
# =========================================================
# UTILIDADES
# =========================================================

def normalizar(texto):
    texto = texto.lower().strip()
    texto = ''.join(
        c for c in unicodedata.normalize('NFD', texto)
        if unicodedata.category(c) != 'Mn'
    )
    return texto


def generar_embedding(texto):
    return client.embeddings.create(
        model=MODEL_EMBED,
        input=texto
    ).data[0].embedding


def asegurar_usuario(uid):
    with driver.session() as session:
        session.run("""
        MERGE (u:Usuario {id:$uid})
        ON CREATE SET 
            u.nivel_general = "basico",
            u.creado = date()
        """, {"uid": uid})


# =========================================================
# STATE
# =========================================================

class Estado(TypedDict, total=False):
    usuario_id: str
    pregunta: str
    embedding: List[float]
    conceptos: List[str]
    contexto: str
    respuesta: str
    nivel: str
    recomendaciones: List[str]
    debug: List[str]


# =========================================================
# NODO 1: PREPARAR
# =========================================================

def nodo_preparar(state: Estado):
    asegurar_usuario(state["usuario_id"])
    return state


# =========================================================
# NODO 2: EMBEDDING
# =========================================================

def nodo_embedding(state: Estado):
    state["embedding"] = generar_embedding(state["pregunta"])
    return state


# =========================================================
# NODO 3: VECTOR SEARCH (Neo4j)
# =========================================================

def nodo_retrieval(state: Estado):

    with driver.session() as session:
        result = session.run("""
        CALL db.index.vector.queryNodes(
            'concepto_embedding_index',
            $top_k,
            $embedding
        )
        YIELD node, score
        RETURN node.nombre AS nombre, score
        """, {
            "embedding": state["embedding"],
            "top_k": TOP_K
        })

        data = list(result)

    state["conceptos"] = [r["nombre"] for r in data]
    state["debug"] = [f"{r['nombre']} ({r['score']:.3f})" for r in data]

    return state


# =========================================================
# NODO 4: MULTI-HOP CONTEXTO
# =========================================================

def construir_contexto(conceptos):

    if not conceptos:
        return "Sin contexto"

    with driver.session() as session:
        result = session.run("""
        MATCH p = (c:Concepto)-[*1..2]-(n)
        WHERE c.nombre IN $conceptos
        RETURN c.nombre AS origen, n.nombre AS destino
        LIMIT 40
        """, {"conceptos": conceptos})

        lineas = [f"{r['origen']} → {r['destino']}" for r in result]

    return "\n".join(lineas) if lineas else "Sin contexto"


def nodo_contexto(state: Estado):
    state["contexto"] = construir_contexto(state["conceptos"])
    return state


# =========================================================
# NODO 5: EVALUAR NIVEL
# =========================================================

def nodo_nivel(state: Estado):

    prompt = f"""
Clasifica el nivel de esta pregunta:
{state['pregunta']}

Opciones: basico, intermedio, avanzado

Responde solo la categoria.
"""

    r = client.responses.create(model=MODEL_CHAT, input=prompt)
    state["nivel"] = r.output_text.strip().lower()

    return state


# =========================================================
# NODO 6: RESPUESTA ADAPTATIVA
# =========================================================

def nodo_respuesta(state: Estado):

    nivel = state.get("nivel", "basico")

    if "basico" in nivel:
        estilo = "explica de forma sencilla con ejemplos"
    elif "intermedio" in nivel:
        estilo = "explica con procesos y relaciones"
    else:
        estilo = "explica con detalle técnico"

    prompt = f"""
Eres un tutor en educación ambiental.

Pregunta:
{state['pregunta']}

Nivel del estudiante:
{nivel}

Contexto del grafo:
{state['contexto']}

Instrucciones:
- {estilo}
- usa el contexto
- no inventes relaciones
- si falta información, dilo
"""

    r = client.responses.create(model=MODEL_CHAT, input=prompt)
    state["respuesta"] = r.output_text.strip()

    return state


# =========================================================
# NODO 7: MEMORIA
# =========================================================

def nodo_memoria(state: Estado):

    with driver.session() as session:
        session.run("""
        MATCH (u:Usuario {id:$uid})
        MATCH (c:Concepto)
        WHERE c.nombre IN $conceptos

        MERGE (u)-[r:APRENDIO]->(c)
        SET r.veces = coalesce(r.veces,0)+1
        """, {
            "uid": state["usuario_id"],
            "conceptos": state["conceptos"]
        })

    return state


# =========================================================
# NODO 8: RECOMENDACIONES
# =========================================================

def nodo_recomendacion(state: Estado):

    with driver.session() as session:
        result = session.run("""
        MATCH (u:Usuario {id:$uid})-[:APRENDIO]->(c1)
        MATCH (c1)-[]-(c2:Concepto)
        WHERE NOT EXISTS {
            MATCH (u)-[:APRENDIO]->(c2)
        }
        RETURN DISTINCT c2.nombre AS rec
        LIMIT 3
        """, {"uid": state["usuario_id"]})

        state["recomendaciones"] = [r["rec"] for r in result]

    return state


# =========================================================
# GRAFO
# =========================================================

builder = StateGraph(Estado)

builder.add_node("prep", nodo_preparar)
builder.add_node("emb", nodo_embedding)
builder.add_node("ret", nodo_retrieval)
builder.add_node("ctx", nodo_contexto)
builder.add_node("nivel", nodo_nivel)
builder.add_node("resp", nodo_respuesta)
builder.add_node("mem", nodo_memoria)
builder.add_node("rec", nodo_recomendacion)

builder.set_entry_point("prep")

builder.add_edge("prep", "emb")
builder.add_edge("emb", "ret")
builder.add_edge("ret", "ctx")
builder.add_edge("ctx", "nivel")
builder.add_edge("nivel", "resp")
builder.add_edge("resp", "mem")
builder.add_edge("mem", "rec")

graph = builder.compile()


# =========================================================
# RUN
# =========================================================

def tutor(pregunta):

    result = graph.invoke({
        "pregunta": pregunta,
        "usuario_id": USUARIO_ID
    })

    #print("\n🔍 Conceptos:")
    #for d in result.get("debug", []):
        #print("-", d)

    #print("\n📘 Respuesta:\n", result["respuesta"])

    #print("\n🧠 Nivel:", result["nivel"])

    #print("\n🎯 Recomendaciones:")
    #for r in result.get("recomendaciones", []):
        #print("-", r)


if __name__ == "__main__":
    while True:
        q = input("\nPregunta: ")
        if q == "salir":
            break
        tutor(q)