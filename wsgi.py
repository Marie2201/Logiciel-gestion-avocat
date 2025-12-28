from app import app

# Gunicorn cherchera "app" dans ce module
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=False)
