"""Flask application entry point: wiring only, no business logic."""

import logging

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

from server.config import Config, PROJECT_ROOT
from server.routes.chat import chat_bp
from server.routes.health import health_bp
from server.routes.history import history_bp

CLIENT_DIR = PROJECT_ROOT / "client"
API_PATHS = {"chat", "history", "health"}


def create_app() -> Flask:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    app = Flask(__name__, static_folder=None)
    CORS(app)

    app.register_blueprint(health_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(history_bp)

    @app.get("/")
    def index():
        return send_from_directory(CLIENT_DIR, "index.html")

    @app.get("/<path:filename>")
    def client_files(filename):
        if filename in API_PATHS:
            return jsonify({
                "ok": False,
                "error": {"code": "method_not_allowed", "message": "Wrong HTTP method."},
            }), 405
        return send_from_directory(CLIENT_DIR, filename)

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify({"ok": False, "error": {"code": "not_found", "message": "Unknown endpoint."}}), 404

    @app.errorhandler(405)
    def method_not_allowed(_error):
        return jsonify({"ok": False, "error": {"code": "method_not_allowed", "message": "Wrong HTTP method."}}), 405

    @app.errorhandler(Exception)
    def unhandled(error):
        app.logger.exception("Unhandled server error: %s", error)
        return jsonify({
            "ok": False,
            "error": {"code": "internal_error", "message": "Unexpected server error."},
        }), 500

    return app


app = create_app()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=Config.FLASK_PORT,
        debug=(Config.FLASK_ENV == "development"),
    )
