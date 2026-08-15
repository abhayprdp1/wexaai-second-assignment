import os
import sys
import logging
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory
from neo4j import GraphDatabase
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
log = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
# Also search in benchmark folder for .env to share credentials
load_dotenv(Path(__file__).parent.parent / "benchmark" / ".env")

COGNODB_URI = os.getenv("COGNODB_URI")
COGNODB_USER = os.getenv("COGNODB_USER", "cognodb")
COGNODB_PASSWORD = os.getenv("COGNODB_PASSWORD")

if not COGNODB_URI or not COGNODB_PASSWORD:
    log.error("Missing database environment credentials.")
    sys.exit(1)

driver = GraphDatabase.driver(COGNODB_URI, auth=(COGNODB_USER, COGNODB_PASSWORD))

app = Flask(__name__, static_folder="static")

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")

@app.route("/<path:path>")
def static_proxy(path):
    return send_from_directory(app.static_folder, path)

@app.route("/api/search", methods=["GET"])
def search():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"movies": [], "actors": []})
        
    with driver.session() as session:
        # Parameterized search queries
        movies_res = session.run(
            "MATCH (m:Movie) WHERE toLower(m.title) CONTAINS toLower($q) RETURN m.id AS id, m.title AS title, m.year AS year, m.rating AS rating LIMIT 10",
            q=query
        )
        actors_res = session.run(
            "MATCH (a:Actor) WHERE toLower(a.name) CONTAINS toLower($q) RETURN a.id AS id, a.name AS name LIMIT 10",
            q=query
        )
        
        movies = [{"id": r["id"], "title": r["title"], "year": r["year"], "rating": r["rating"]} for r in movies_res]
        actors = [{"id": r["id"], "name": r["name"]} for r in actors_res]
        
    return jsonify({"movies": movies, "actors": actors})

@app.route("/api/movie/<movie_id>", methods=["GET"])
def get_movie(movie_id):
    with driver.session() as session:
        # Get movie details & director
        movie_res = session.run(
            "MATCH (m:Movie {id: $id}) "
            "OPTIONAL MATCH (d:Director)-[:DIRECTED]->(m) "
            "RETURN m.title AS title, m.year AS year, m.rating AS rating, m.overview AS overview, d.name AS director, d.id AS director_id",
            id=movie_id
        ).single()
        
        if not movie_res:
            return jsonify({"error": "Movie not found"}), 404
            
        # Get Cast (1-hop)
        cast_res = session.run(
            "MATCH (a:Actor)-[r:ACTED_IN]->(m:Movie {id: $id}) RETURN a.id AS id, a.name AS name, r.role AS role",
            id=movie_id
        )
        cast = [{"id": r["id"], "name": r["name"], "role": r["role"]} for r in cast_res]
        
        # Get Genres
        genres_res = session.run(
            "MATCH (m:Movie {id: $id})-[:BELONGS_TO]->(g:Genre) RETURN g.name AS name",
            id=movie_id
        )
        genres = [r["name"] for r in genres_res]
        
        # Recommendation Cypher query (2-hop traversal)
        # Find movies sharing same genres or actors, sorted by connection strength
        rec_res = session.run(
            "MATCH (m:Movie {id: $id})-[:BELONGS_TO]->(g:Genre)<-[:BELONGS_TO]-(rec:Movie) "
            "WHERE rec <> m "
            "RETURN rec.id AS id, rec.title AS title, count(g) AS common_genres "
            "ORDER BY common_genres DESC, rec.rating DESC LIMIT 5",
            id=movie_id
        )
        recommendations = [{"id": r["id"], "title": r["title"]} for r in rec_res]
        
    return jsonify({
        "title": movie_res["title"],
        "year": movie_res["year"],
        "rating": movie_res["rating"],
        "overview": movie_res["overview"],
        "director": movie_res["director"],
        "director_id": movie_res["director_id"],
        "cast": cast,
        "genres": genres,
        "recommendations": recommendations
    })

@app.route("/api/actor/<actor_id>", methods=["GET"])
def get_actor(actor_id):
    with driver.session() as session:
        # Get actor details
        actor_res = session.run(
            "MATCH (a:Actor {id: $id}) RETURN a.name AS name, a.born AS born",
            id=actor_id
        ).single()
        
        if not actor_res:
            return jsonify({"error": "Actor not found"}), 404
            
        # Get Movies Acted In (1-hop)
        movies_res = session.run(
            "MATCH (a:Actor {id: $id})-[r:ACTED_IN]->(m:Movie) RETURN m.id AS id, m.title AS title, r.role AS role, m.year AS year",
            id=actor_id
        )
        movies = [{"id": r["id"], "title": r["title"], "role": r["role"], "year": r["year"]} for r in movies_res]
        
        # Get Co-stars (2-hop traversal via Movie node)
        costars_res = session.run(
            "MATCH (a:Actor {id: $id})-[:ACTED_IN]->(m:Movie)<-[:ACTED_IN]-(co:Actor) "
            "RETURN co.id AS id, co.name AS name, count(m) AS movies_together "
            "ORDER BY movies_together DESC LIMIT 8",
            id=actor_id
        )
        costars = [{"id": r["id"], "name": r["name"], "weight": r["movies_together"]} for r in costars_res]
        
    return jsonify({
        "name": actor_res["name"],
        "born": actor_res["born"],
        "movies": movies,
        "costars": costars
    })

@app.route("/api/path", methods=["GET"])
def get_path():
    start_name = request.args.get("start", "").strip()
    end_name = request.args.get("end", "").strip()
    if not start_name or not end_name:
        return jsonify({"error": "Start and End actor names are required"}), 400
        
    with driver.session() as session:
        # Find shortest path between two actors using variable-length path query
        # actor1 -> acted_in -> movie -> acted_in -> actor2
        path_res = session.run(
            "MATCH p = shortestPath((a1:Actor)-[*..10]-(a2:Actor)) "
            "WHERE toLower(a1.name) = toLower($start) AND toLower(a2.name) = toLower($end) "
            "RETURN p",
            start=start_name, end=end_name
        ).single()
        
        if not path_res:
            return jsonify({"path": []})
            
        path_obj = path_res["p"]
        nodes = []
        relationships = []
        
        for node in path_obj.nodes:
            labels = list(node.labels)
            label = labels[0] if labels else "Unknown"
            name = node.get("name") or node.get("title")
            nodes.append({
                "id": node.get("id"),
                "label": label,
                "name": name
            })
            
        for rel in path_obj.relationships:
            relationships.append({
                "type": rel.type,
                "role": rel.get("role", "")
            })
            
    return jsonify({
        "nodes": nodes,
        "relationships": relationships
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
