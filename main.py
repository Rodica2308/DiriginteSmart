from app import app  # Import Flask app

if __name__ == "__main__":
    # Rulează aplicația în modul de dezvoltare
    print("Server starting at: http://0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000, debug=True)
