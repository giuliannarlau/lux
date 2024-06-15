/**
 * Toggle the check state of all checkboxes based on the source button.
 * @param {HTMLInputElement} source - The input button that triggered the function ('fund'or 'refund').
*/
function selectAll(source) {
    // TODO: handle when user checks/unchecks all after selecting one ore more projects

    // Store the list of checkboxes
    let checkboxes;

    // Determine which group os checkboxes to select based on button clicked
    if (source.value == "selectAllFunds") {
        console.log("Inside if funds");
        checkboxes = document.getElementsByName("fund_checkbox");
    }
    else if (source.value == "selectAllRefunds") {
        checkboxes = document.getElementsByName("refund_checkbox");
    }
    else {
        console.log("Invalid button");
    }

    // Toggle the checked state for all checkboxes
    for (let i=0; i < checkboxes.length; i++) {
        if (checkboxes[i].type == "checkbox") {
            if (checkboxes[i].checked == true) {
                checkboxes[i].checked = false;
            } else {
                checkboxes[i].checked = true;
            }
        }
    }
};


/**
 * Send the projects selected by admin to the server and builds a modal with response.
 * @param {string} operationType - The type of operation to perform ('fund' or 'refund').
*/
async function buildAdminOperationsModal(operationType) {

    // Query all projects from table
    const projectRows = document.querySelectorAll(".projectRow2");
    const selectedProjectsIds = [];
    
    // Fetch the IDs of checked projects
    projectRows.forEach((row) => {
        const checkbox = row.querySelector(".admin-project-checkbox");
        if (checkbox.checked) {
            const projectId = checkbox.value;
            selectedProjectsIds.push(projectId);
        }
    });

    // Alert and exit if no project is selected
    if (selectedProjectsIds.length === 0) {
        alert("Please select at least one project.");
        return;
    }

    try {
        // Send the selected project ids to the server
        const responseFund = await fetch("/control_panel", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Operation-Type": operationType,
            },
            body: JSON.stringify({ selected_projects_ids: selectedProjectsIds }),
        });

        // Parse the server response 
        let data = await responseFund.json();
        let responseProjects = data.admin_action_projects;

        // Get projects form from modal
        const projectsForm = document.getElementById("projectsForm");
        projectsForm.innerHTML = "";

        // Create a new table to display server response with project information
        const table = document.createElement("table");
        table.classList.add("table");
        table.setAttribute("project_id", "modalAdminTable");

        // Create header row and populate with column titles
        const headerRow = document.createElement("tr");
        const headers = ["ID", "Name", "Destination Account", "Donations"];
        headers.forEach((headerText) => {
            const headerCell = document.createElement("th");
            headerCell.textContent = headerText;
            headerRow.appendChild(headerCell);
        });

        // Add header to table
        table.appendChild(headerRow);

        // Add a row for each project
        responseProjects.forEach((project) => {
            const dataRow = document.createElement("tr");
            dataRow.classList.add("fundProjectRow");

            const idCell = document.createElement("td");
            idCell.textContent = project.project_id;
            dataRow.appendChild(idCell);

            const nameCell = document.createElement("td");
            nameCell.textContent = project.name;
            dataRow.appendChild(nameCell);

            const publicKeyCell = document.createElement("td");
            publicKeyCell.textContent = project.public_key;
            dataRow.appendChild(publicKeyCell);

            const donationsCell = document.createElement("td");
            donationsCell.textContent = project.total_donations;
            dataRow.appendChild(donationsCell);

            // Append row to table
            table.appendChild(dataRow);
        });

        // Add the table to the form element
        projectsForm.appendChild(table);

        // Initialize and display the modal
        const modal = new bootstrap.Modal(document.getElementById("projectsModal"));
        modal.show();

        // Build transaction with one operation per row and send it to Stellar
        processAdminTransaction(responseProjects, operationType);
    } catch (error) {
        console.log("Error: ", error);
    }
};


/**
 * Processes administrative transactions by sending them to the server and handling the response.
 * @param {Array} responseProjects - The projects involved in the transaction.
 * @param {string} operationType - The type of administrative operation to perform.
 */
function processAdminTransaction(responseProjects, operationType) {

    // Get the submit button from modal
    let submitTransactionButton = document.getElementById("submitTransactionButton");
    submitTransactionButton.addEventListener("click", async function () {
        try {
            const requestOptions = {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Operation-Type': operationType,
                },
                body: JSON.stringify({ admin_operations: responseProjects })
            };

            let response = await fetch("/build_admin_transaction", requestOptions);
            let data = await response.json();

            // Get transaction XDR for admin to sign
            let transactionXdr = data.transaction_xdr

            // Sign transaction using Freighter extension
            let signedTransaction = await signingTransaction(transactionXdr);
            
            let modalTitle = document.getElementById("modalTitle")
            let modalBody = document.getElementById("modalBody")

            // Update the modal to display a processing transaction message
            modalTitle.innerHTML = "Processing your transfer...";
            modalBody.textContent = "Please wait while we process your transaction.";
            
            // Block closing modal options
            setModalLockState("lock");

            // Send the signed transaction to Stellar and get hash response
            let hash = await sendTransaction(signedTransaction);

            // Update the modal with confirmation and the transaction hash
            modalTitle.innerHTML = "Transaction completed!";
            modalBody.textContent = "Here is your hash:\n" + hash;

            // Allow user to close modal
            setModalLockState("unlock");
        } catch (error) {
            console.log("Error: ", error);
        }
    });
};