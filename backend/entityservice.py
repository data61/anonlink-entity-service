import json
import os
import logging
from contextlib import closing
import psycopg2

from flask import Flask, g

import anonlink


# Config

# Hard coded default configuration can be overwritten with environment variables
# Or a configuration file.

# Postgres Database Details
DATABASE_SERVER = os.environ.get('DATABASE_SERVER', 'db')
DATABASE_USER = os.environ.get('DATABASE_USER', 'postgres')
DATABASE_PASSWORD = os.environ.get('DATABASE_PASSWORD', 'mysecretpassword')
DATABASE = 'postgres'

PER_PAGE = 30
DEBUG = os.environ.get("DEBUG", "false") == "true"
SKIP_AUTH = os.environ.get("SKIP_AUTH", "false") == "true"
SECRET_KEY = 'development key'

# Logging
LOGFILE = os.environ.get("LOGFILE", 'entity-service-application.log')
fileFormat = logging.Formatter('%(asctime)-15s %(name)-12s %(levelname)-8s: %(message)s [in %(pathname)s:%(lineno)d]')
consoleFormat = logging.Formatter('%(asctime) %(name)-12s: %(levelname)-8s %(message)s', datefmt="%m-%d %H:%M")

# Logging setup
fileHandler = logging.FileHandler(LOGFILE)
fileHandler.setLevel(logging.DEBUG)
fileHandler.setFormatter(fileFormat)
consoleHandler = logging.StreamHandler()
consoleHandler.setLevel(logging.INFO)
consoleHandler.setFormatter(consoleFormat)


app = Flask(__name__)
app.logger.addHandler(fileHandler)
app.logger.addHandler(consoleHandler)
app.logger.setLevel(logging.DEBUG)


def connect_db():
    host = app.config['DATABASE_SERVER']
    user = app.config['DATABASE_USER']
    pw = app.config['DATABASE_PASSWORD']
    db = app.config['DATABASE']

    try:
        conn = psycopg2.connect(database=db, user=user, password=pw, host=host)
    except psycopg2.OperationalError:
        app.logger.warning("warning connecting to default postgres db")
        conn = psycopg2.connect(database='postgres', user=user, password=pw, host=host)
    return conn


def get_db():
    """Opens a new database connection if there is none yet for the
    current application context.
    """
    db = getattr(g, '_db', None)
    if db is None:
        db = g._db = connect_db()
    return db


def init_db():
    """Initializes the database (only run if required)."""
    # The database name
    db = app.config['DATABASE']

    # Check if the database exists
    with closing(connect_db()) as conn:
        cur = conn.cursor()
        cur.execute("""SELECT count(*) from pg_database WHERE datname = %s""", (db,))
        if cur.fetchone()[0] == 1:
            app.logger.info("Database already exists")
            return

        app.logger.info("Database doesn't exist yet")

        conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
        conn.cursor().execute("CREATE DATABASE {};".format(db))
        app.logger.info("DB created")

    app.logger.info("Creating tables")
    with closing(connect_db()) as conn:
        with app.open_resource('schema.sql', mode='r') as f:
            conn.cursor().execute(f.read())
        conn.commit()
    app.logger.info("Tables created")


def query_db(query, args=(), one=False):
    """
    Queries the database and returns a list of dictionaries.

    https://flask-doc.readthedocs.org/en/latest/patterns/sqlite3.html#easy-querying
    """
    with get_db().cursor() as cur:
        cur.execute(query, args)
        rv = [dict((cur.description[idx][0], value)
                   for idx, value in enumerate(row)) for row in cur.fetchall()]
    return (rv[0] if rv else None) if one else rv


@app.before_request
def before_request():
    g.db = connect_db()


@app.teardown_request
def teardown_request(exception):
    if hasattr(g, 'db'):
        g.db.close()

@app.route('/danger/init')
def init():
    init_db()
    return 'Ok'


@app.route('/status')
def status():
    return 'Ok'

@app.route('/stats')
def stats():
    """Displays the latest mapping statistics"""

    number_of_mappings = query_db('''
        select COUNT() from mappings
        where *
        ''', one=True)

    return json.dumps({'number_mappings': number_of_mappings})


@app.route('/version')
def version():
    return 'anonlink: {}'.format(anonlink.__version__)


@app.route('/danger/test')
def test():

    samples = 200
    nl = anonlink.randomnames.NameList(samples * 2)
    s1, s2 = nl.generate_subsets(samples, 0.75)
    keys = ('test1', 'test2')
    filters1 = anonlink.entitymatch.calculate_bloom_filters(s1, nl.schema, keys)
    filters2 = anonlink.entitymatch.calculate_bloom_filters(s2, nl.schema, keys)
    similarity = anonlink.entitymatch.calculate_filter_similarity(filters1, filters2)
    mapping = anonlink.network_flow.map_entities(similarity, threshold=0.95, method='weighted')
    return json.dumps(mapping)


@app.route('/create-mapping', methods=["POST"])
def create_mapping():
    mapping_id = "123"

    return 'Creating mapping'


@app.route('/update', methods=["POST"])
def update_mapping():
    return 'Update mapping'


@app.route('/calculate-mapping', methods=["POST"])
def calculate_mapping():

    similarity = anonlink.entitymatch.calculate_filter_similarity(filters1, filters2)
    mapping = anonlink.network_flow.map_entities(similarity, threshold=0.95, method='weighted')
    return json.dumps(mapping)



if __name__ == '__main__':
    app.run()
