import os
import sqlite3

from stellar_sdk import Server


# Horizon server
horizon_server = Server("https://horizon-testnet.stellar.org")

# Project's images directory
IMAGE_UPLOAD_DIR = "static/images/projects"

# Add categories here
categories_list = ["books", "education", "environment", "finance", "games", "music", "technology"]

# Projects are updated to this statuses
status_list = ["active", "fund", "refund", "successful", "unsuccessful"]

# Builds the absolute path to SQLite database
base_dir = os.path.abspath(os.path.dirname(__file__))
database_path = os.path.join(base_dir, 'database', 'crowdfunding.db')

# Create connection with SQLITE database
def get_db_connection():
    conn = sqlite3.connect(database_path)
    conn.row_factory = sqlite3.Row
    return conn