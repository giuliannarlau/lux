import os
import time
import traceback

from dotenv import load_dotenv
load_dotenv()

from config import categories_list, status_list, horizon_server
from flask import Flask, jsonify, make_response, redirect, render_template, request, session, url_for

from stellar_sdk.exceptions import BadResponseError, BadRequestError

from helpers import *

app = Flask(__name__)

# Configure your secret key and admin account in the .env file
app.secret_key = os.environ.get('SECRET_KEY')
admin_account = os.environ.get('ADMIN_ACCOUNT')


@app.context_processor
def global_variables():
    """ Variables used on templates """
    return dict(
        categories_list=categories_list,
        status_list=status_list,
        admin_account=admin_account
    )


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/", methods=["GET", "POST"])
def index():
    """
    Displays homepage and deals with connecting Freighter wallet.

    GET method: access homepage, displaying active projects.
    POST method: update project status to refund or unsuccessful (canceled projects won't be funded even if they have achieved the goal amount).

    Returns:
        GET: renders index.html.
        POST: return success response or 500 error.
    """

    # Timing
    start_time_total = time.time()

    if request.method == "POST":

        # Forget any user_id
        session.clear()

        try:
            # Get Freighter public key and store within session
            public_key = request.data.decode("utf-8")
            session["public_key"] = public_key
            return make_response("Connected.", 200)

        except Exception as e:
            print(str(e))
            return handle_response("Internal server error.")

    projects_list = search_projects(status="active")

    end_time_total = time.time()
    print(f"Time tracking: {end_time_total - start_time_total} sec")

    return render_template("index.html", projects_list=projects_list)


@app.route("/logout")
def logout():
    """ Disconnects wallet: forgets the public key and redirects to homepage."""
    session.clear()
    return redirect("/")


@app.route("/about", methods=["GET", "POST"])
def about():
    """ Displays About Us page. """
    return render_template("about.html")


@app.route("/faq")
def faq():
    """ Displays FAQ page with commom questions. """
    return render_template("faq.html")


@app.route("/projects", methods=["GET", "POST"])
def projects():
    """
    Displays projects page with a list of all projects.

    GET method: displays full projects list.

    Returns:
        GET: renders projects.html.
    """
    projects_list = search_projects() 
    return render_template("projects.html", projects_list=projects_list)


@app.route("/filter_projects", methods=["POST"])
def filter_projects():
    """
    Filter projects based on search criteria inputed by the user.

    Params (POST form): name, category and status.

    Returns:
        Success: renders the specific parent page with the correspondent projects.
        Failure: detailed error message.
    """

    try:
        # Get search criteria from user
        project_search = {
            "name": request.form.get("searchProjectName").lower(),
            "category": request.form.get("searchProjectCategory").lower(),
            "status": request.form.get("searchProjectStatus").lower()
        }

        # Handle all categories and statuses
        if project_search["category"] == "all":
            project_search["category"] = ""
        if project_search["status"] == "all":
            project_search["status"] = ""

        # Search projects with the filters inputed by the user
        projects_list = search_projects(project_search["name"], project_search["category"], project_search["status"])

        # Get origin page (search bar is a template shared by multiple pages)
        parent_page = request.form.get("parent_page")
        
        # Filter only current user's projects for My Projects page
        if parent_page == "my_projects.html" and session["public_key"] != admin_account:
            projects_list = [project for project in projects_list if project["public_key"] == session["public_key"]]

        return render_template(parent_page, projects_list=projects_list)
    except Exception as e:
        print(str(e))
        return handle_response("Error filtering projects.")


@app.route("/project/<int:project_id>", methods=["GET", "POST"])
def project_page(project_id):
    """
    Displays details of a specific project and allows the owner to cancel it.

    GET method: renders the project details page.
    POST method: update project status to refund or unsuccessful.

    Returns:
        GET: renders project.html with project details.
        POST: return success or failure response of the cancelation process.
    """

    try:
        project = search_project_by_id(project_id)
    except Exception as e:
        print(str(e))
        return handle_response(str(e))
    
    # Handle project cancelation
    if request.method == "POST":
        
        try:
            # Set new status (canceled projects cannot be funded)
            new_status = "refund"
            if project["total_donations"] == 0:
                new_status = "unsuccessful"
                
            # Updates table projects with new status
            query = "UPDATE projects SET status = ? WHERE id = ?"
            params = (new_status, project_id)
            write_query(query, params)
            return handle_response("Project canceled.")
        except Exception as e:
            print(e)
            return handle_response(str(e))
    
    # Display project's page or not found error
    return render_template('project.html', project=project)


@app.route("/my_projects")
@freighter_required
def my_projects():
    """
    Displays all projects created by the current user.
    Admin users are redirected to the control panel page.

    Returns:
        Redirects admin user to the control panel.
        Renders my_projects.html with current user's projects.
    """

    # Redirect admin to control panel page
    if session["public_key"] == admin_account:
        return redirect("/control_panel")
    
    # Search and filter only projects owned by the user
    projects_list = search_projects()
    projects_list = [project for project in projects_list if project["public_key"] == session["public_key"]]

    return render_template("my_projects.html", projects_list=projects_list)


@app.route("/my_donations")
@freighter_required
def my_donations():
    """
    Displays the current user's donations and the projects they've supported.
    Admin users are redirected to the control panel page.

    Returns:
        Renders my_donations.html with a list of donations and supported projects.
    """
    # TODO: see if indeed the admin will be redirected to control panel (can make donations)
    if session["public_key"] == admin_account:
        return redirect("/control_panel")

    # Searches all user's donations with hashes
    user_donations = search_donations_history()

    # Searches details of donations per project
    supported_projects = search_supported_projects()

    return render_template("my_donations.html",
                           user_donations_list=user_donations,
                           supported_projects=supported_projects)


@app.route("/new_project", methods=["GET", "POST"])
@freighter_required
def new_project():
    """
    Allows a connected user to create a new project.

    GET method: displays the page to create a new project.
    POST method: processes the submitted form and creates the project.

    Params (POST form): project data inserted by the user.

    Returns:
        GET: renders the new_project.html template.
        POST: redirects to the created project's page or renders an error.
    """

    if request.method == "POST":

        try:
            # Parse and format the expiration date from the form input
            expire_date = format_date(request.form.get("projectExpireDate"), "long_string")
            
            # Get project info inputed by the user
            project = {
                "category": request.form.get("projectCategory"),
                "goal": request.form.get("projectGoal"),
                "name": request.form.get("projectName"),
                "expire_date": expire_date,
                "status": "active",
                "description": request.form.get("projectDescription"),
                "image": request.form.get("base64Image")
            }
            
            # Check for invalid or malicious inputs
            check_input(project)
            
            # Upload image in the static folder ang get url
            file_url = upload_image(project["image"], app)

            # Insert project info and image url into projects table
            project_id = insert_project_into_database(project, file_url)
            return redirect(url_for("project_page", project_id=project_id))
        except ValueError as e:
            print(str(e))
            return handle_response(f"{str(e)}")
        except Exception as e:
            print(str(e))
            return handle_response(f"{str(e)}")

    return render_template("new_project.html")


@app.route("/edit_project", methods=["POST"])
def edit_project():
    """
    Allows the project owner to edit details of the project.

    POST method: processes the form to edit the project details and updates it.

    Params (POST form): new project info inputed by the user on the form.

    Returns:
        POST: redirects to the same project page with the updated info.
    """

    try:
        # Parse and format the expiration date from the form input
        expire_date = format_date(request.form.get("newExpireDate"), "long_string")
        
        # Get current project id and new project info inputed by the user
        project = {
            "id": request.form.get("projectId"),
            "category": request.form.get("newCategory"),
            "goal": request.form.get("newGoal"),
            "name": request.form.get("newName"),
            "expire_date": expire_date,
            "description": request.form.get("newDescription")
        }

        # Prevent invalid or malicious inputs
        check_input(project)
        
        # Update table projects
        query = """
            UPDATE projects
            SET name = ?, category = ?, goal = ?, expire_date = ?,
            description = ?
            WHERE id = ?
        """
        params = (
            project["name"],
            project["category"].lower(),
            project["goal"],
            project["expire_date"],
            project["description"],
            project["id"])
        
        write_query(query, params)
        return redirect(url_for("project_page", project_id=project["id"]))
    except ValueError as e:
        print(str(e))
        return handle_response(str(e))
    except Exception as e:
        print(str(e))
        return handle_response(str(e))


@app.route("/donate", methods=["POST"])
def donate():
    """
    Processes a donation to a project.

    POST method: receives the donation data in JSON format,
    execute validations and builds the payment transaction.

    Params (JSON): project_id, amount.

    Returns:
        Success: JSON response with the transaction details.
        Error: error message for invalid requests.
    """

    try:
        # Get donation info
        data = request.get_json()
        project_id = data.get("project_id")
        amount = data.get("amount")

        # Get project info from database
        project_data = fetch_query("""
            SELECT status, public_key
            FROM projects WHERE id = ?
        """, project_id,)[0]

        # Check if project is active (not expired)
        if project_data["status"] != "active":
            return handle_response("Expired projects can't receive donations.")
        
        # Prevent self-donation
        if project_data["public_key"] == session["public_key"]:
            return handle_response("Self donations are not allowed.")

        # Validate the donation amount
        if not check_amount(amount):
            return handle_response("Invalid amount.")

        # Prepare operation
        operation_data = [{
            "project_id": project_id,
            "amount": amount,
            "source_account": session["public_key"],
            "destination_account": admin_account,
        }]

        # Build the payment transaction and return xdr transaction
        transaction_xdr = build_payment_transaction(operation_data, "donation")
        return jsonify(transaction_xdr=str(transaction_xdr))
    except Exception as e:
        print(str(e))
        return handle_response({str(e)})
    

@app.route("/send_transaction", methods=["POST"])
@freighter_required
def send_transaction():
    """
    Submits a signed transaction to the Stellar network.

    POST method: receives a signed transaction in JSON format, submits it to the network,
    and updates the database with the transaction's hash.

    Params (POST form): signed transaction in XDR format.

    Returns:
        Success: JSON response including the transaction submission response.
        Failure: detailed error message.
    """

    try:
        # Retrieve signed transaction from request and submit it to Stellar
        signed_transaction = request.get_json()
        submit_response = horizon_server.submit_transaction(signed_transaction)

        if submit_response["successful"] == True:
            try:
                # Get transaction hash
                hash = submit_response["hash"]

                # Insert hash and transaction data into database
                insert_transaction_into_database(hash)
                return jsonify(submit_response)
            except Exception as e:
                print(str(e))
                return handle_response(str(e))

    except Exception as e:
        print(str(e))
        return handle_response(f"Unexpected error sending transaction: {str(e)}")
    


""" ADMIN ROUTES """

@app.route("/control_panel", methods=["GET", "POST"])
@freighter_required
def control_panel():
    """
    Control panel for admin to manage the project's transactions.

    GET method: displays projects tabs categorized by fund, refund and all projects.
    POST method: processes admin actions on selected projects based on operation type.

    Returns:
        GET: renders control_panel.html with all projects.
        POST: returns JSON response with details of admin actions on selected projects.
    """

    # Display forbidden error to commom users
    if session["public_key"] != admin_account:
        return handle_response("Only an admin can access this page.")

    projects_list = search_projects()

    if request.method == "POST":
        admin_action_projects = []

        try:
            # Get operation type and selected project IDs from request
            operation_type = request.headers.get("Operation-Type")
            request_data = request.get_json()
            selected_projects_ids = [int(id) for id in request_data.get("selected_projects_ids")]

            # Filter only projects that are fundable or refundable
            admin_action_projects = filter_permitted_projects(
                projects_list,
                selected_projects_ids,
                operation_type
            )

            # Get total refund amount per project and donor from transactions table
            if operation_type == "refund":
                admin_action_projects = search_refund_operations(admin_action_projects)
            return jsonify(admin_action_projects=admin_action_projects)
        except Exception as e:
            print(str(e))
            handle_response(str(e))

    return render_template("control_panel.html", projects_list=projects_list)


@app.route("/build_admin_transaction", methods=["POST"])
@freighter_required
def build_admin_transaction():
    """
    Builds and returns xdr transaction for admin operations (fund and refund).

    Params (POST form):
        - admin_operations: a list where each item contains project_id and total_donations.

    Returns:
        Success: JSON response with the xdr.
        Failure: detailed error message.
    """

    try:
        # Get operation type selected by admin (fund or refund)
        operation_type = request.headers.get("Operation-Type")
        
        request_data = request.get_json()
        data = request_data.get("admin_operations")

        admin_operations = [
            {
                "project_id": project["project_id"],
                "amount": project["total_donations"],
                "source_account": admin_account,
                "destination_account": project["public_key"],
            }
            for project in data
        ]

        transaction_xdr = build_payment_transaction(admin_operations, operation_type)
        return jsonify(transaction_xdr=str(transaction_xdr))
    except Exception as e:
        print(str(e))
        return handle_response({str(e)})


if __name__ == "__main__":
    with app.app_context():
        
        update_expired_projects_statuses()
        context = ('cert.pem', 'key.pem')

    app.run(debug=True, ssl_context=context)