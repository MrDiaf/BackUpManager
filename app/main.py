from waitress import serve

import db
from web import app, engine, load_password

if __name__ == "__main__":
    db.init()
    app.config["PASSWORD"] = load_password()
    engine.start()
    print("Backup manager listening on port 8095", flush=True)
    serve(app, host="0.0.0.0", port=8095, threads=4)
