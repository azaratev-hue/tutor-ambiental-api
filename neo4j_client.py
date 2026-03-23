# -*- coding: utf-8 -*-
"""
Created on Sun Mar 22 23:16:36 2026

@author: azara
"""

from neo4j import GraphDatabase
import os

class Neo4jClient:

    def __init__(self):
        self.driver = GraphDatabase.driver(
            os.getenv("NEO4J_URI"),
            auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD"))
        )

    def close(self):
        self.driver.close()

    def guardar_aprendizaje(self, usuario_id, conceptos):

        query = """
        MERGE (u:Usuario {id: $usuario_id})

        WITH u

        UNWIND $conceptos AS concepto

        MERGE (c:Concepto {nombre: concepto})

        MERGE (u)-[:APRENDIO]->(c)
        """

        with self.driver.session() as session:
            session.run(query, usuario_id=usuario_id, conceptos=conceptos)
            
    def actualizar_nivel_usuario(self, usuario_id):
        query = """
        MATCH (u:Usuario {id: $usuario_id})
        OPTIONAL MATCH (u)-[:APRENDIO]->(c:Concepto)
        WITH u, COUNT(DISTINCT c) AS total_conceptos
    
        SET u.nivel_general =
            CASE
                WHEN total_conceptos <= 5 THEN 'basico'
                WHEN total_conceptos <= 12 THEN 'intermedio'
                ELSE 'avanzado'
            END
    
        RETURN u.nivel_general AS nivel, total_conceptos
        """
    
        with self.driver.session() as session:
            result = session.run(query, usuario_id=usuario_id)
            record = result.single()
            return {
                "nivel": record["nivel"],
                "total_conceptos": record["total_conceptos"]
            }
