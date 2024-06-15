# Lux Crowdfunding

## Overview

Lux is a blockchain-based crowdfunding platform developed as the final project for Harvard's CS50 course. It uses the Stellar network's TESTNET and the Freighter wallet to enable users to launch and support crowdfunding projects. The admin account is responsible for funding or refunding projects after they expire and must be registered into the .env file to process these transactions.

## Technologies

- **Backend**: Python 3.11.4, Flask 3.0.2.
- **Frontend**: HTML, CSS, Jinja2 3.1.3, and Bootstrap 5.3.0.
- **Database**: SQLite3 3.45.2.

## Initial Setup

### Creating a Freighter account
1. Visit [Freighter](https://www.freighter.app/) to install the extension and create a wallet.
2. Ensure you are set on the TESTNET network.

### Installation

1. Ensure Python is installed.

2. Obtain a self-signed SSL certificate and place `cert.pem` and `key.pem` in the root directory.

3. Clone the repository:  
`git clone https://github.com/giuliannarlau/crowdfunding.git`.

4. Create and activate a virtual environment:  
`python -m venv venv`
   - **Windows**: `.\venv\Scripts\activate`
   - **macOS and Linux**: `source venv/bin/activate`

5. Install dependencies:  
`pip install -r requirements.txt`.

7. Configure environment variables:  
   - Copy `.env.sample` to `.env`.
   - Generate a secure Flask Secret Key and input it next to `SECRET_KEY=`:
   ```
   python -c 'import secrets; print(secrets.token_hex())'
   ```
   - Obtain the public key of a Freighter wallet that will be used as the admin account and input it next to `ADMIN_ACCOUNT=`.

8. Start the application:  
`python app.py`.

### Usage
- For users:
   - Donations: users can easily contribute to projects by signing transactions through Freighter's browser extension.
   - Creating projects: users can also launch new projects by specifying details such as title, funding goals, expiry date, category, and more. A project can be edited or canceled.
- For admin:
   - Funding and refunding: admins can manage funds and refunds through the control panel, utilizing Freighter for transaction signing.

### Project Structure
- `/templates`: contains individual templates for each page and shared templates in the `includes` subdirectory.
- `/static`: contains common logic and styling files. Specific logic files are named after their corresponding HTML template.
   - `/images`: stores project images (`/projects`) and website-specific images (`/site`).
- `/database`: includes tables for projects, transactions, and temporary transaction data.
- `/root`: Contains the Flask application (`app.py`) and auxiliary functions (`helpers.py`).



