from flask_migrate import Migrate
from app import create_app
from models import db
from models.user import User
from models.client import Client

app = create_app()
migrate = Migrate(app, db)

@app.shell_context_processor
def ctx():
    return {"db": db, "User": User, "Client": Client}
