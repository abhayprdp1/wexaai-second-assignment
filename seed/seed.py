import os
import json
import logging
from pathlib import Path
from dotenv import load_dotenv
from neo4j import GraphDatabase

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
log = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
# Also search in parent directory for .env
load_dotenv(Path(__file__).parent.parent / ".env")

COGNODB_URI = os.getenv("COGNODB_URI")
COGNODB_USER = os.getenv("COGNODB_USER", "cognodb")
COGNODB_PASSWORD = os.getenv("COGNODB_PASSWORD")

if not COGNODB_URI or not COGNODB_PASSWORD:
    # Try looking in the benchmark project .env
    benchmark_env = Path(__file__).parent.parent.parent / "benchmark" / ".env"
    if benchmark_env.exists():
        load_dotenv(benchmark_env)
        COGNODB_URI = os.getenv("COGNODB_URI")
        COGNODB_USER = os.getenv("COGNODB_USER", "cognodb")
        COGNODB_PASSWORD = os.getenv("COGNODB_PASSWORD")

if not COGNODB_URI or not COGNODB_PASSWORD:
    log.error("COGNODB_URI and COGNODB_PASSWORD must be set in environment variables.")
    exit(1)

DATA_PATH = Path(__file__).parent / "data.json"

def seed_database():
    log.info("Connecting to CognoDB Cloud at %s ...", COGNODB_URI)
    driver = GraphDatabase.driver(COGNODB_URI, auth=(COGNODB_USER, COGNODB_PASSWORD))
    
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)[0]
        
    with driver.session() as session:
        # Clear database
        log.info("Clearing existing database...")
        session.run("MATCH (n) DETACH DELETE n")
        
        # Create unique constraint on Movie(id) and Actor(id), Director(id)
        log.info("Creating constraints...")
        try: session.run("CREATE CONSTRAINT FOR (m:Movie) REQUIRE m.id IS UNIQUE")
        except Exception: pass
        try: session.run("CREATE CONSTRAINT FOR (a:Actor) REQUIRE a.id IS UNIQUE")
        except Exception: pass
        try: session.run("CREATE CONSTRAINT FOR (d:Director) REQUIRE d.id IS UNIQUE")
        except Exception: pass
        try: session.run("CREATE CONSTRAINT FOR (g:Genre) REQUIRE g.name IS UNIQUE")
        except Exception: pass
        
        # Load Genres
        log.info("Loading genres...")
        for genre in data["genres"]:
            session.run("MERGE (g:Genre {name: $name})", name=genre)
            
        # Load Movies
        log.info("Loading movies...")
        movie_query = """
        UNWIND $movies AS movie
        MERGE (m:Movie {id: movie.id})
        SET m.title = movie.title,
            m.year = movie.year,
            m.rating = movie.rating,
            m.overview = movie.overview
        """
        session.run(movie_query, movies=data["movies"])
        
        # Load Actors
        log.info("Loading actors...")
        actor_query = """
        UNWIND $actors AS actor
        MERGE (a:Actor {id: actor.id})
        SET a.name = actor.name,
            a.born = actor.born
        """
        session.run(actor_query, actors=data["actors"])
        
        # Load Directors
        log.info("Loading directors...")
        director_query = """
        UNWIND $directors AS director
        MERGE (d:Director {id: director.id})
        SET d.name = director.name,
            d.born = director.born
        """
        session.run(director_query, directors=data["directors"])
        
        # Load ACTED_IN
        log.info("Creating ACTED_IN relationships...")
        acted_query = """
        UNWIND $acted_in AS edge
        MATCH (a:Actor {id: edge.actor})
        MATCH (m:Movie {id: edge.movie})
        MERGE (a)-[r:ACTED_IN]->(m)
        SET r.role = edge.role
        """
        session.run(acted_query, acted_in=data["acted_in"])
        
        # Load DIRECTED
        log.info("Creating DIRECTED relationships...")
        directed_query = """
        UNWIND $directed AS edge
        MATCH (d:Director {id: edge.director})
        MATCH (m:Movie {id: edge.movie})
        MERGE (d)-[:DIRECTED]->(m)
        """
        session.run(directed_query, directed=data["directed"])
        
        # Load Movie Genres
        log.info("Creating Genre relationships...")
        genre_rel_query = """
        UNWIND $movie_genres AS item
        MATCH (m:Movie {id: item.movie})
        UNWIND item.genres AS gname
        MATCH (g:Genre {name: gname})
        MERGE (m)-[:BELONGS_TO]->(g)
        """
        session.run(genre_rel_query, movie_genres=data["movie_genres"])
        
        # Create CO_STARRED_WITH derived relationships to make traversals super fast
        log.info("Creating derived CO_STARRED_WITH relationships...")
        session.run("""
        MATCH (a1:Actor)-[:ACTED_IN]->(m:Movie)<-[:ACTED_IN]-(a2:Actor)
        WHERE id(a1) < id(a2)
        WITH a1, a2, count(m) as weight
        MERGE (a1)-[r:CO_STARRED_WITH]-(a2)
        SET r.weight = weight
        """)

    driver.close()
    log.info("Database seeding complete!")

if __name__ == "__main__":
    seed_database()
