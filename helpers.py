import base64
import math
import os
import secrets
import traceback

from datetime import datetime
from config import IMAGE_UPLOAD_DIR, get_db_connection, categories_list, horizon_server
from flask import redirect, render_template, request, session
from functools import wraps
from stellar_sdk import Asset, Network, TransactionBuilder
from stellar_sdk.exceptions import NotFoundError

admin_account = os.environ.get('ADMIN_ACCOUNT')


""" QUERIES """

def fetch_query(query, params=()):
    """
    Executes a SELECT SQL query with optional parameters and returns the fetched results.
    
    Params:
        query (str): SQL query string for data retrieval.
        params (tuple, optional): parameters tuple for the SQL query.
    
    Returns:
        list: list of dictionaries representing fetched rows,
        or an empty list in case of an exception.
    """
    try:
        # Establish a new db connection and create a new cursor
        conn = get_db_connection()
        cursor = conn.cursor()

        # Ensure the params are a tuple
        if not isinstance(params, tuple):
            params = (params,)

        # Execute query and return a list of dictionaries
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"Error in fetch query execution: {e}")
        return []
    finally:
        # Close cursor and db connection
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def write_query(query, params=()):
    """
    Executes an SQL query for database modification with optional parameters.
    
    Params:
        query (str): SQL query string for data modification.
        params (tuple, optional): parameters tuple for the SQL query,
        defaults to tuple ().
    
    Return:
        Success: this function doesn't return anything.
        Failure: raises a detailed error.
    """
    try:
        # Establish a new db connection and create a new cursor
        conn = get_db_connection()
        cursor = conn.cursor()

        # Ensure the params are a tuple
        if not isinstance(params, tuple):
            params = (params,)

        # Execute and commit changes to database
        cursor.execute(query, params)
        conn.commit()
    except Exception as e:

        # Roll back any changes made during the transaction in case of an error
        conn.rollback()
        raise Exception(f"Error writing query into database: {str(e)}.")
    finally:
        # Close cursor and db connection
        cursor.close()
        conn.close()


""" FORMATTING  """

def format_date(date_str, to_type):
    """
    Formats a date string into a specified format.

    Params:
        date_str (str): the date string to format.
        date_format (str): the target format of the date string.

    Returns:
        str: the formatted date string, or None if the input format is incorrect.
    """

    # String dates with time are inserted on database ("YYYY-MM-DD HH:MM:SS")
    if to_type == "long_string":
        return f"{date_str} 23:59:59"

    # Medium dates are shown on client side (MM/DD/YYYY)
    if to_type == "medium_string":
        try:

            # Parse to datetime to change format and split and return as a str
            date = datetime.strptime(date_str.split(" ")[0], "%Y-%m-%d")
            return date.strftime("%m/%d/%Y")
        except ValueError as e:
            raise ValueError(f"Error formatting date: {str(e)}")
        except Exception as e:
            raise Exception(f"Unexpected error in formatting date: {str(e)}")
    

""" PAYMENTS """

def build_payment_transaction(operations_list, operation_type):
    """
    Builds one operation per project, grouping into one transaction.
    Each transaction has it's own operation type (donation for users and fund/refund for admin)
    
    Params:
        - operations_list: list of dictionaries, each containing:
            'project_id', 'total_donations', 'source_account', and 'destination_account'
        - operation_type: string with the operation to process:
            'donation', 'fund', or 'refund'

    Returns:
        A string with the transaction in XDR format for the user to sign.
    """

    # Check if destination account exists
    for operation in operations_list:
        try:
            horizon_server.load_account(operation["destination_account"])
        except NotFoundError:
            raise NotFoundError("This destination account doesn't exists.")

    try:
        # Set the source acccount (for donations is the user account, for funds and refunds is the admin account)
        public_key_sender = admin_account if operation_type in ["fund", "refund"] else operations_list[0]["source_account"]
        
        # Get transaction fee from Stellar Network
        base_fee = horizon_server.fetch_base_fee()

        # Load the source account (admin) to proper type
        source_account = horizon_server.load_account(public_key_sender)
        
        # Build transaction
        transaction = (
            TransactionBuilder(
                source_account=source_account,
                network_passphrase=Network.TESTNET_NETWORK_PASSPHRASE,
                base_fee=base_fee,
            )
        )

        # Fetch temporary transactions data from database
        temp_transactions_list = fetch_query("SELECT * FROM temp_operations")

        # Clear table if it's not empty
        if temp_transactions_list:
            write_query("DELETE FROM temp_operations")

        # Append payment operations for each project
        for operation in operations_list:
            transaction.append_payment_op(
                destination=operation["destination_account"],
                asset=Asset.native(),
                amount=str(operation["amount"])
            )

            # Temporarily save operations to update database after submitting the transaction
            query = """
                INSERT INTO temp_operations
                (project_id, amount, destination_account, type)
                VALUES(?, ?, ?, ?)
            """
            params = (
                operation["project_id"],
                operation["amount"], operation["destination_account"], operation_type
            )
            write_query(query, params)

        # Set max timelimit (in seconds) to process transaction
        transaction.set_timeout(30)
        transaction = transaction.build()

        # Convert transaction to XDR format and return for signing
        transaction_xdr = transaction.to_xdr()
        return transaction_xdr
    except Exception as e:
        raise Exception(f"Error building payment transaction: {str(e)}")


""" CALCULATE """

def calculate_total_donations(projects_list):
    """
    Calculates the total donations for each project in the provided list.

    Params:
        projects_list (list): list of project dictionaries to update with total donations.

    Returns:
        list: the updated list of project dictionaries including total donations.
    """

    try:
        # Sum donations by project id
        query = "SELECT project_id, SUM(amount) as donations FROM transactions WHERE type = ? GROUP BY project_id"
        params = ("donation",)
        total_donations = fetch_query(query, params)

        # Convert results into a dict mapping projects id to total donations
        donations_dict = {row['project_id']: row['donations'] for row in total_donations}

        # Add total donations to projects list
        for project in projects_list:
            project["total_donations"] = donations_dict.get(project["project_id"], 0)
        return projects_list
    except Exception as e:
        print("Error getting donations: ", str(e))


def calculate_project_days_left(projects_list):
    """
    Calculates the number of days left until the expiration of each project in the list, updating each project's dictionary with the result.

    Params:
        projects_list (list): list of project dictionaries, each containing project details.

    Returns:
        list: the same list with each dictionary updated to include the number of days left until the project's expiration.
    """
    for project in projects_list:
        if project["status"] == "active":
            expire_date = datetime.strptime(project["expire_date"], "%Y-%m-%d %H:%M:%S")
            days_remaining = expire_date - datetime.today()
            days_left = days_remaining.days
            
            # Custom format
            if days_left == 0:
                project["days_left"] = "last day"
            elif days_left == 1:
                project["days_left"] = "{} day left".format(days_left)
            else:
                project["days_left"] = "{} days left".format(days_left)
        else:
            project["days_left"] = 0

    return projects_list


def calculate_project_progress(projects_list):
    """
    Calculates the funding progress of each project as a percentage of the goal amount, updating each project's dictionary with the result.
    
    Params:
        projects_list (list): list of project dictionaries, each containing project details including total donations and goal.

    Returns:
        list: the same list with each dictionary updated to include the project's funding progress percentage.
    """
    
    try:
        # Calculate sum of donations per project
        projects_list = calculate_total_donations(projects_list)

        for project in projects_list:

            # Calculate and add to the list the funding progress in percentage
            project["funding_progress"] = f'{math.floor(project["total_donations"] / project["goal"] * 100)}%'
        return projects_list
    except Exception as e:
        print("Error calculating project progress: ", str(e))
        return None


""" VALIDATION """

def check_amount(value):
    """
    Validates if the provided value is a positive integer.
    
    Params:
        value (str): the value to be validated as a positive integer.
    
    Returns:
        bool: True if the value is a valid, positive integer, False otherwise.
    """

    try:
        int_value = int(value)
    except:
        return False
    
    return int_value > 0
    

def check_input(project):
    """
    Validates project details to ensure they meet specific criteria.

    Params:
        project (dict): dictionary containing the project details to be validated.

    Returns:
        Union[str, bool]: True if all validations pass, otherwise returns a string message indicating the first validation failure.
    """
    # TODO: Change it, too many if's

    for key, value in project.items():
        
        # Prevent insertion of empty values into the database
        if not value:
            raise ValueError(f"Field {key} is empty.")
        
        # Ensure expiration date is in the future and correctly formatted
        if key == "expire_date":
            try:
                expire_date = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
                if expire_date < datetime.today():
                    raise ValueError(f"Invalid date {expire_date}: past expiration dates are not allowed.")
            except ValueError:
                raise ValueError(f"Invalid date {expire_date}: incorrect format.")
        
        # Ensure the category is previous registered
        if key == "category" and value.lower() not in categories_list:
            raise ValueError(f"Value '{value}' is not a valid {key}.")

        # Ensure the goal amount is positive
        if key == "goal" and not check_amount(value):
            raise ValueError(f"Value '{value}' is not a valid {key}.")


def filter_permitted_projects(projects_list, selected_projects_ids, operation_type):
    """
    Filters projects from a list where the project IDs match those specified and the project's current status matches the operation type.
    
    Params:
        projects_list (list): list of project dictionaries to filter from.
        selected_projects_ids (list): list of project IDs to filter the projects by.
        operation_type (str): the required status each project must have to pass the filter.

    Returns:
        list: a filtered list of project dictionaries that meet the criteria.
    """
    
    # Keep track of allowed project for chosen operation
    projects_checked = []

    # For each project in the database
    for project in projects_list:
        try:
            # Prevent fund/refund of unexistant or active projects, as well as projects without donations
            if project["project_id"] in selected_projects_ids and project["status"] == operation_type:
                projects_checked.append(project)
        except Exception as e:
            raise Exception(f"Unexpected error in filter permitted projects: {str(e)}")
    return projects_checked


""" SEARCHES """

def search_donations_history():
    """
    Searches for a detailed donation history based on name, category, and status filters.

    Returns:
        list: list of dictionaries where each dictionary represents a donation made by the user.
    """

    try:
        # Fetch all user's donations
        query = """
            SELECT t.project_id, p.name, p.category, t.amount, t.timestamp, t.hash FROM transactions t 
            JOIN projects p ON t.project_id = p.id 
            WHERE t.public_key_sender = ? AND t.type = ?
        """
        params = (session["public_key"], "donation")
        donations_history = fetch_query(query, params)

        # Format friendly date
        for donation in donations_history:
            donation["timestamp"] = format_date(donation["timestamp"], "medium_string")

        return donations_history
    except Exception as e:
        print("Error searching donation history:", str(e))
        return []


def search_projects(name="", category="", status=""):
    """
    Searches for projects data based on optional parameters such as project's name, category and status.
    It integrates additional processing like calculating project days left and project funding progress.

    Params:
        name (str, optional): filter by the project's name. Defaults to an empty string.
        category (str, optional): filter by the project's category. Defaults to an empty string.
        status (str, optional): filter by the project's status. Defaults to an empty string.

    Returns:
        list: detailed list of project dictionaries or empty list.
    """

    projects_list = []

    try:
        # Fetch all projects that correspond to the criteria
        query ="""
            SELECT id AS project_id, name, category, status, public_key, 
            expire_date, goal, image_path, description FROM projects 
            WHERE name LIKE ? AND category LIKE ? AND status LIKE ? 
            ORDER BY created_at DESC, status
        """
        params = ("%" + name + "%", "%" + category + "%", "%" + status + "%")

        projects_list = fetch_query(query, params)

        # Calculate the amount of days left for each project
        projects_list = calculate_project_days_left(projects_list)

        # Format friendly date
        for project in projects_list:
            project["expire_date"] = format_date(project["expire_date"], "medium_string")

        # Calculate the current percentage of funding reached
        return calculate_project_progress(projects_list)
    except Exception as e:
        print("Error searching projects:", str(e))
        return []


def search_project_by_id(id):
    """
    Searches for a project by its ID.
    It integrates additional processing like calculating project days left and project funding progress.

    Params: id (int)

    Returns:
        dict: project data.
    """
    try:
        # Fetch project info from database
        query ="""
            SELECT id AS project_id, name, category, status, public_key, 
            expire_date, goal, image_path, description FROM projects 
            WHERE id = ? 
        """
        params = (id,)
        projects = fetch_query(query, params)

        # Deal with unexistent project
        if not projects:
            raise Exception(f"Project with ID {id} not found.")
        
        # Calculate the amount of days left for each project
        projects = calculate_project_days_left(projects)

        # Format friendly date
        for project in projects:
            project["expire_date"] = format_date(project["expire_date"], "medium_string")

        # Calculate the current percentage of funding reached
        return calculate_project_progress(projects)[0]
    except Exception as e:
        raise Exception(f"Error searching project by ID: {str(e)}")


def search_refund_operations(projects_list):
    """
    Searches for total donation amounts per donor for each project in a provided list.

    Params:
        projects_list (list): list of project dictionaries, each containing project details.

    Returns:
        list: list of dictionaries, each representing a refund operation.
        Contains the project ID, donor's public key, and total amount to be refunded.
    """

    refundable_projects = []

    try:
        for project in projects_list:

            # Fetch total donations by donor for the project to build an operation
            query = """
                SELECT project_id, public_key_sender AS public_key,
                SUM(amount) AS total_donations 
                FROM transactions
                WHERE project_id = ? AND type = ?
                GROUP BY public_key_sender
            """
            params = (project["project_id"], "donation")
            donations_by_donor = fetch_query(query, params)
            
            # Add project name to each operation
            for operation in donations_by_donor:
                operation["name"] = project["name"]

            # Update final list of doners to be refunded
            refundable_projects.extend(donations_by_donor)
        return refundable_projects
    except Exception as e:
        raise Exception(f"Error searching refund operations: {str(e)}")


def search_supported_projects():
    """
    Searches for projects supported by the current user, aggregating the total donations made by the user to each project.

    Returns:
        list: list of dictionaries, each representing a project (with its details) supported by the user.
    """

    try:

        # Fetch sum of donations by project
        query = """
            SELECT t.project_id, p.name, p.category, p.status, p.goal, SUM(amount) AS your_donations FROM transactions t 
            JOIN projects p ON t.project_id = p.id 
            WHERE t.public_key_sender = ? AND t.type = ? GROUP BY t.project_id ORDER BY p.status
        """
        params = (session["public_key"], "donation")
        projects_list = fetch_query(query, params)

        # Calculate the current percentage of funding reached
        return calculate_project_progress(projects_list)
    except Exception as e:
        print("Error searching supported projects:", e)
        return []


""" UPDATES """

def insert_project_into_database(project, file_url):
    """
    Inserts a new project into the database using provided project details and an image URL.

    Params:
        project (dict): a dictionary containing project details such as name, category, goal, etc.
        file_url (str): the URL of the project's image.

    Returns:
        int: the ID of the newly inserted project, or an error message in case of failure.
    """
    try:

        # Insert the project data and image file url into the projects table
        query = """
            INSERT INTO projects (public_key, name, category, goal, expire_date, status, image_path, description, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            session["public_key"], 
            project["name"], 
            project["category"].lower(), 
            project["goal"], 
            project["expire_date"],
            project["status"],
            file_url, 
            project["description"],
            datetime.now()
        )
        write_query(query, params)

        # Fetch and return the ID of the newly inserted project
        query = "SELECT id FROM projects ORDER BY created_at DESC LIMIT 1"
        result = fetch_query(query)
        return result[0]["id"]
    except Exception as e:
        print(str(e))
        return str(e)
        

def insert_transaction_into_database(hash):
    """
    Updates the transactions table with the transaction data and adjusts project statuses following administrative fund or refund actions.

    Params:
        hash (str): the transaction hash to be recorded with each transaction entry.

    Returns:
        None
    """
    try:
        # Fetch ongoing transactions from temporary table
        temp_table = fetch_query("SELECT * FROM temp_operations")

        # TODO: this is stupid, I'm doing that twice, its easier just to store the keys in the temp table
        for operation in temp_table:

            if operation["type"] == "donation":
                public_key_sender = session["public_key"]

                # Donations are tranferred to the admin account
                public_key_receiver = admin_account

            else:
                # Fund and refund transactions must be sended by admin
                public_key_sender = admin_account

                # Receiver for funding is project's creator and for refunding is the donor
                public_key_receiver = operation["destination_account"]

                # Set new status for projects that are being funded or refunded
                if operation["type"] == "fund":
                    new_status = "successful"
                else:
                    new_status = "unsuccessful"

                # Update project status
                query = "UPDATE projects SET status = ? WHERE id = ?"
                params = (new_status, operation["project_id"])
                write_query(query, params)

            # Insert transaction data into the transactions table
            query = """
            INSERT INTO transactions (project_id, amount, public_key_sender, public_key_receiver, hash, type, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            params = (
                    operation["project_id"],
                    operation["amount"],
                    public_key_sender,
                    public_key_receiver,
                    hash,
                    operation["type"],
                    datetime.now()
            )
            write_query(query, params)
    except Exception as e:
        print(str(e))
        raise Exception(f"Error updating transactions database: {str(e)}")


def update_expired_projects_statuses():
    """
    Updates the status of projects based on their expiry date and total donations compared to their goals.

    Params:
        projects_list (list): list of dictionaries, each containing
        the details of a project.

    Returns:
        bool: True if the status update operation is successful for all projects, False otherwise.
    """
    try:

        # Fetch active projects
        projects_list = fetch_query("""
            SELECT id AS project_id, status, expire_date, goal
            FROM projects WHERE status = 'active'
        """)

        # If there isn't any, nothing needs to be done
        if not projects_list:
            return True
        
        # Calculate total amount of donations per project
        projects_list = calculate_total_donations(projects_list)

        for project in projects_list:

            # Parse expiration date to datetime format
            project["expire_date"] = datetime.strptime(project["expire_date"], "%Y-%m-%d %H:%M:%S")

            if project["expire_date"] < datetime.today():

                # Donations are refunded when project doesn't meet the goal
                new_status = "refund"
                
                # Projects that achieved their goal will be funded by admin
                if project["total_donations"] >= project["goal"]:
                    new_status = "fund"

                # Projects without donations pass directly to unsuccessful
                if project["total_donations"] == 0:
                    new_status = "unsuccessful"
                
                # Updates the project status
                query = "UPDATE projects SET status = ? WHERE id = ?"
                params = (new_status, project["project_id"])
                write_query(query, params)
        
        return True
    except Exception as e:
        print(f"Error changing status: {str(e)}")
        return False


def upload_image(base64_img, app):
    """
    Uploads an image to the server by decoding the provided Base64 image string and saving it to a predefined directory.

    Params:
        base64_img (str): the Base64-encoded image string to be decoded and saved.
        app (Flask): the Flask application instance.

    Returns:
        str: the file URL of the uploaded image.
    """

    try:
        # Decode to bytes avoiding padding error
        image_str = base64_img.split(",")[1]
        image_bytes = base64.b64decode(image_str + "==")

        # Generate a secure filename
        random_hex = secrets.token_hex(8)
        filename = random_hex + ".png"

        # Get directory path from config.py
        upload_dir = IMAGE_UPLOAD_DIR
        file_path = os.path.join(upload_dir, filename)

        with open(file_path, 'wb') as f:
            f.write(image_bytes)

        file_url = os.path.join('static', 'images', 'projects', filename)

        return file_url
    except Exception as e:
        print("Error uploading image:", e)
        return e


""" OTHER """

def handle_response(message):
    """
    Renders an error or success message to the user.

    Params:
        message (str): the message to be displayed to the user.
        code (int, optional): the HTTP status code associated with the message. Defaults to 400.

    Returns:
        render_template: the rendered HTML template displaying the message and code.
    """
    return render_template("handle_response.html", bottom=message, referrer=request.headers.get("Referer"))


def freighter_required(f):
    """
    A decorator function for Flask routes that requires the user to be connected with Freighter.

    Params:
        f (function): the Flask route function to be decorated.

    Returns:
        function: the decorated Flask route function, which redirects to the homepage if the user is not connected with freighter.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("public_key") is None:
            return handle_response("To access this page, please connect your wallet.")
        return f(*args, **kwargs)
    return decorated_function
