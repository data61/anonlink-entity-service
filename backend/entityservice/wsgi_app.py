import connexion

con_app = connexion.FlaskApp(__name__, specification_dir='api_def', debug=True)
app = con_app.app
